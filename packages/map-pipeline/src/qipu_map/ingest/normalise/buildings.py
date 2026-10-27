"""Buildings: the City's 2015 footprints dated by the tax roll, plus the OSM buildings the survey does not have.

The rules:
- A footprint takes the year of the parcel its centroid stands on, and no nearer parcel when it stands on none: a pier
  or a building on a road allowance stays undated rather than borrowing a neighbour's year.
- A parcel's year is the most common year built among its roll rows. A strata tower has one row per unit, all with the
  tower's year; a stray row with the old lot's year (1951 among 149 rows of 2021) must not date the tower (the oldest
  row would draw it in the 1950s). Ties go to the oldest year. The roll only describes buildings standing today, so a
  garage takes its house's year.
- When the parcel's rows agree on a later big-improvement year, it goes out as `year_improved`: a heritage house kept
  in front of a tower added behind it (a 1928 house, its tower 1989) is one footprint and one roll year, and only the
  improvement year tells the eras stage when the tall part came.
- An OSM building is new when less than 30 % of its area lies on survey footprints. Matching by overlap, not by id,
  is the only link the two datasets have; 30 % lets a slightly shifted outline still count as the same building.
- A new building takes its OSM date tag; else its parcel's roll year when that year can only be its own (see
  `new_building_year`); else `footprint_survey_year` (2016 for footprints traced in 2015), flagged `convention`:
  a past-year render then never shows it.
- An OSM height whose storeys cannot hold it (over 7 m a storey) is not trusted; a storey count alone becomes a height
  at 3.4 m a storey for homes, 4.2 m for offices and shops, 3.8 m otherwise.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import shapely
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from qipu_map.ingest.normalise.geojson import Feature, polygons, raw_features
from qipu_map.ingest.normalise.osm import Element, area_shape, elements, metres, osm_id, year_of
from qipu_map.values import as_int, most_common

NEW_SHARE = 0.30  # an OSM outline with less than this share on survey footprints is a building the survey lacks
SAME_SHARE = 0.60  # both outlines this much inside each other: one building, so OSM's height applies to the footprint
MIN_AREA_M2 = 20.0
MAX_STOREY_M = 7.0
YEAR_RANGE = (1850, 2100)  # the roll writes 1800 for "unknown"

SKIP_TYPES = frozenset(
    {
        "roof",
        "carport",
        "construction",
        "ruins",
        "demolished",
        "no",
        "collapsed",
        "bridge",
        "houseboat",
        "storage_tank",
        "silo",
        "tent",
        "ship",
        "boat",
        "container",
        "abandoned",
        "proposed",
        "disused",
        "razed",
        "shelter",
        "kiosk",
        "toilets",
        "gazebo",
        "pavilion",
        "static_caravan",
        "transformer_tower",
        "bunker",
    }
)
HOMES = frozenset(
    {
        "house",
        "detached",
        "semidetached_house",
        "bungalow",
        "terrace",
        "townhouse",
        "residential",
        "apartments",
        "dormitory",
        "hotel",
    }
)
WORK = frozenset({"commercial", "office", "retail", "supermarket", "shop", "mall"})


@dataclass(frozen=True)
class Parcel:
    year_built: int | None
    zoning: str | None
    year_improved: int | None = None
    rows: int = 1


def parcels_from_roll(rows: Iterable[dict[str, Any]]) -> dict[str, Parcel]:
    """Roll rows (one per property) folded to one record per parcel: the most common valid year built, the most common
    later big-improvement year, the first zoning district."""
    years: dict[str, list[int]] = {}
    improved: dict[str, list[int]] = {}
    zones: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()
    for r in rows:
        coord = str(r.get("land_coordinate") or "").strip()
        if not coord:
            continue
        counts[coord] += 1
        years.setdefault(coord, [])
        improved.setdefault(coord, [])
        zones.setdefault(coord, [])
        y, bi = _year(r.get("year_built")), _year(r.get("big_improvement_year"))
        if y is not None:
            years[coord].append(y)
            if bi is not None and bi > y:
                improved[coord].append(bi)
        if r.get("zoning_district"):
            zones[coord].append(str(r["zoning_district"]).strip())
    out = {}
    for c, built in years.items():
        year = most_common(built)
        later = [v for v in improved[c] if year is not None and v > year]
        improved_year = most_common(later) if len(later) * 2 > len(built) else None
        out[c] = Parcel(year, min(zones[c]) if zones[c] else None, improved_year, counts[c])
    return out


def _year(v: Any) -> int | None:
    y = as_int(v)
    return y if y is not None and YEAR_RANGE[0] <= y <= YEAR_RANGE[1] else None


class ParcelIndex:
    """Parcel polygons that carry a tax coordinate, and the roll record of the one a point stands on."""

    def __init__(self, parcel_shapes: dict[str, Any], roll: dict[str, Parcel]) -> None:
        self.shapes: list[BaseGeometry] = []
        self.coords: list[str] = []
        for g, p in raw_features(parcel_shapes):
            if p.get("tax_coord"):
                self.shapes.append(g)
                self.coords.append(str(p["tax_coord"]))
        self.tree = STRtree(self.shapes)
        self.roll = roll

    def coord_at(self, point: shapely.Point) -> str | None:
        """The parcel under the point. Where parcels are stacked (air-space parcels over one lot, 9 of them under one
        Davie Street tower), the dated one with the most roll rows: the first by number is often an undated shell."""
        hits = sorted(self.coords[i] for i in self.tree.query(point, predicate="within"))
        if not hits:
            return None
        best: str = min(hits, key=self._rank)
        return best

    def _rank(self, coord: str) -> tuple[int, int, str]:
        p = self.roll.get(coord)
        return (0 if p and p.year_built is not None else 1, -(p.rows if p else 0), coord)

    def at(self, point: shapely.Point) -> Parcel | None:
        coord = self.coord_at(point)
        return self.roll.get(coord) if coord else None


def survey_buildings(footprints: dict[str, Any], parcels: ParcelIndex, source: str = "footprints") -> list[Feature]:
    """The footprints, each with the year and zoning of the parcel under its centroid."""
    out = []
    for g, p in raw_features(footprints):
        parts = polygons(g)
        if not parts:
            continue
        outline = parts[0]
        parcel = parcels.at(outline.centroid)
        year = parcel.year_built if parcel else None
        props = _props(
            year=year,
            year_source="tax_roll" if year is not None else None,
            year_improved=parcel.year_improved if parcel else None,
            height=None,
            levels=None,
            use=parcel.zoning if parcel else None,
            source=source,
        )
        out.append(Feature(f"van15-{p['object_id']}", outline, props))
    return out


def _props(
    *,
    year: int | None,
    year_source: str | None,
    height: float | None,
    levels: int | None,
    use: str | None,
    source: str,
    year_improved: int | None = None,
) -> dict[str, Any]:
    return {
        "year_built": year,
        "year_source": year_source,
        "year_improved": year_improved,
        "height_m": height,
        "levels": levels,
        "use": use,
        "source": source,
    }


def osm_height(tags: dict[str, str]) -> tuple[float | None, int | None]:
    """(height in metres, storeys) from OSM tags, either one None when OSM does not say."""
    h = metres(tags.get("height"))
    lv = metres(tags.get("building:levels"))
    levels = int(lv) if lv and lv > 0 else None
    if h is not None and h > 0 and not (levels and h / levels > MAX_STOREY_M):
        return round(h, 2), levels
    if levels:
        kind = tags.get("building", "yes")
        storey = 3.4 if kind in HOMES else 4.2 if kind in WORK else 3.8
        return round(levels * storey, 2), levels
    return None, levels


def osm_outlines(raw: dict[str, Any], m2_per_deg2: float) -> list[tuple[Element, shapely.Polygon]]:
    """OSM buildings that stand above ground and are at least 20 m², as (element, largest polygon)."""
    out = []
    for el in elements(raw):
        tags = el["tags"]
        kind = tags.get("building")
        if kind is None or kind in SKIP_TYPES or tags.get("location") in ("underground", "underwater"):
            continue
        if tags.get("layer", "0").startswith("-"):
            continue
        g = area_shape(el)
        parts = polygons(g) if g is not None else []
        if parts and parts[0].area * m2_per_deg2 >= MIN_AREA_M2:
            out.append((el, parts[0]))
    return out


def new_building_year(
    tags: dict[str, str], parcel: Parcel | None, parcel_surveyed: bool, survey_year: int
) -> tuple[int, str]:
    """A date tag first, then the parcel's roll year when it can only be this building's, then the survey-year
    convention.

    On a parcel the survey traced other buildings on, a roll year from before the survey belongs to one of those.
    On a parcel with no survey footprint at all, the survey missed the building, and the roll year is its own.
    """
    year = year_of(tags)
    if year is not None:
        return year, "osm"
    if parcel and parcel.year_built and (not parcel_surveyed or parcel.year_built >= survey_year - 1):
        return parcel.year_built, "tax_roll"
    return survey_year, "convention"


def merge_osm(
    survey: Sequence[Feature], osm: Sequence[tuple[Element, shapely.Polygon]], parcels: ParcelIndex, survey_year: int
) -> list[Feature]:
    """The survey footprints (with OSM heights where OSM maps the same building) and the OSM buildings the survey
    lacks."""
    tree = STRtree([f.geometry for f in survey])
    surveyed = {parcels.coord_at(f.geometry.centroid) for f in survey}
    heights: dict[int, tuple[float | None, int | None]] = {}
    added = []
    for el, outline in osm:
        hits = [(int(i), survey[int(i)].geometry.intersection(outline).area) for i in tree.query(outline)]
        covered = sum(a for _, a in hits) / outline.area
        height, levels = osm_height(el["tags"])
        if covered >= NEW_SHARE:
            for i, a in hits:
                if a >= SAME_SHARE * outline.area and a >= SAME_SHARE * survey[i].geometry.area:
                    heights[i] = (height, levels)
            continue
        coord = parcels.coord_at(outline.centroid)
        parcel = parcels.roll.get(coord) if coord else None
        year, year_source = new_building_year(el["tags"], parcel, coord in surveyed, survey_year)
        kind = el["tags"].get("building")
        props = _props(
            year=year,
            year_source=year_source,
            height=height,
            levels=levels,
            use=kind if kind != "yes" else None,
            source="osm",
        )
        added.append(Feature(osm_id(el), outline, props))
    merged = [
        Feature(f.id, f.geometry, {**f.props, "height_m": heights[i][0], "levels": heights[i][1]})
        if i in heights
        else f
        for i, f in enumerate(survey)
    ]
    return merged + added
