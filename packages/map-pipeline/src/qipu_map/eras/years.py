"""Years for the features of today's scene: dates from the rules file, neighbour years for undated buildings.

These run once on today's scene. Every past scene and every date map reads the same resolved years, so a building
cannot stand from 1912 in one place and 1925 in another.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.eras.rules import Basis, DatedFeature, ImprovedRule, UndatedRule
from qipu_map.hashing import stable_fraction
from qipu_map.model import Building, Street, YearSource


def moment(feature_id: str) -> float:
    """CONVENTION: the point in its year (0.1 to 0.9) when a feature dated only by a year appeared or went.

    A record gives a year, not a day. A fixed draw per feature spreads one year's buildings over that year, so they do
    not all appear on the first of January; the same feature always gets the same moment.
    """
    return 0.1 + 0.8 * stable_fraction(feature_id)


def footprints(buildings: Sequence[Building]) -> NDArray[np.object_]:
    """The footprints as an array of shapely polygons (rings may have any number of points)."""
    out = np.empty(len(buildings), dtype=object)
    out[:] = [shapely.Polygon(b.footprint) for b in buildings]
    return out


def centroids(buildings: Sequence[Building]) -> NDArray[np.float64]:
    """An (n, 2) array of footprint centroids."""
    if not buildings:
        return np.zeros((0, 2))
    return shapely.get_coordinates(shapely.centroid(footprints(buildings))).reshape(-1, 2)


def neighbours(points: NDArray[np.float64], radius: float) -> list[list[int]]:
    """For each point, the indices of the other points within `radius` metres, in increasing index order."""
    out: list[list[int]] = [[] for _ in range(len(points))]
    if len(points) == 0:
        return out
    geoms = np.asarray(shapely.points(points))
    tree = shapely.STRtree(geoms)
    src, dst = tree.query(geoms, predicate="dwithin", distance=radius)
    for i, j in sorted(zip(src.tolist(), dst.tolist(), strict=True)):
        if i != j:
            out[i].append(j)
    return out


def resolve_undated(buildings: Sequence[Building], rule: UndatedRule) -> tuple[Building, ...]:
    """Give every undated building its neighbours' median year (CONVENTION). Dated buildings are returned unchanged."""
    if all(b.year_built is not None for b in buildings):
        return tuple(buildings)
    pts = centroids(buildings)
    dated = np.array([b.year_built is not None for b in buildings])
    years = np.array([b.year_built or 0 for b in buildings], dtype=np.int64)
    tree = shapely.STRtree(shapely.points(pts[dated]))
    dated_years = years[dated]
    out = list(buildings)
    for i, b in enumerate(buildings):
        if b.year_built is not None:
            continue
        year = rule.fallback_year
        for r in rule.radii_m:
            hits = tree.query(shapely.points(pts[i]), predicate="dwithin", distance=r)
            if len(hits):
                year = min(int(np.median(np.sort(dated_years[hits]))), rule.cap_year)
                break
        if b.height_m > rule.tall_m:
            year = max(year, rule.tall_floor_year)
        out[i] = replace(b, year_built=year, year_source=YearSource.CONVENTION)
    return tuple(out)


def apply_dated_buildings(buildings: Sequence[Building], dated: Sequence[DatedFeature]) -> tuple[Building, ...]:
    """Set the years a rules file gives for buildings matched by id (a record whose roll year is known to be wrong)."""
    rules = [d for d in dated if d.layer == "buildings"]
    out = []
    for b in buildings:
        dated_b = b
        for d in rules:
            if d.matches(b.id, None):
                source = YearSource.HISTORICAL if d.basis is Basis.SOURCED else YearSource.CONVENTION
                dated_b = replace(
                    dated_b,
                    year_built=d.opened or b.year_built,
                    demolished=d.closed or b.demolished,
                    year_source=source,
                )
        out.append(dated_b)
    return tuple(out)


def apply_dated_streets(streets: Sequence[Street], dated: Sequence[DatedFeature]) -> tuple[Street, ...]:
    """Set opening and closing years on today's streets, bridges and rail lines matched by id or name."""
    rules = [d for d in dated if d.layer == "streets"]
    out = []
    for s in streets:
        dated_s = s
        for d in rules:
            if d.matches(s.id, s.name):
                dated_s = replace(dated_s, year_opened=d.opened or s.year_opened, year_closed=d.closed or s.year_closed)
        out.append(dated_s)
    return tuple(out)


def switch_date(year: int | None, feature_id: str, a: int, b: int) -> float | None:
    """The decimal date in the segment (a, b] at which a feature dated `year` appears or goes, or None if it is outside.

    A feature dated in year b is in key b, so its date is held at b at the latest.
    """
    if year is None or not a < year <= b:
        return None
    return min(year + moment(feature_id), float(b))


def apply_improvements(buildings: Sequence[Building], rule: ImprovedRule) -> tuple[Building, ...]:
    """Date tall buildings from their big-improvement year when the roll gives a later one (see `ImprovedRule`)."""
    return tuple(
        replace(b, year_built=b.year_improved)
        if b.year_improved and b.year_built and b.year_improved > b.year_built and b.height_m > rule.tall_m
        else b
        for b in buildings
    )
