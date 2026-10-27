"""Streets, lanes, paths and rail as centrelines with a kind and, where a source gives one, a width.

Streets and lanes come from the City, whose street-use classes give each its kind; OSM adds what the City
does not publish as streets: footpaths, cycle paths, steps and rail. A City centreline takes the width of the nearest
right-of-way label within 20 m: that is the property-line to property-line width, the space the street occupies.
The City publishes those widths in feet (66 for a street, 20 for a lane).
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import shapely
from shapely.strtree import STRtree

from qipu_map.ingest.normalise.geojson import Feature, lines, raw_features, shape_id, split_ids
from qipu_map.ingest.normalise.osm import elements, metres, osm_id, way_line

STREET_KIND = {
    "Arterial": "arterial",
    "Secondary Arterial": "arterial",
    "Collector": "arterial",
    "Residential": "residential",
    "Closed": "path",
    "Recreational": "path",
    "Leased": "path",
}
PATHS = frozenset({"footway", "path", "cycleway", "pedestrian", "steps", "bridleway"})
NOT_A_PATH = frozenset({"sidewalk", "crossing", "traffic_island"})  # drawn with their street, not as their own ribbon
RAIL = frozenset({"rail", "light_rail", "tram", "narrow_gauge"})
ROW_REACH_M = 20.0
FOOT_M = 0.3048
_BLOCK_RANGE = re.compile(r"^\d+(?:-\d+)?\s+")


def street_name(hblock: str | None) -> str | None:
    """The hundred-block label minus its range: '1100-1200 PENDRELL ST' is 'PENDRELL ST'."""
    if not hblock:
        return None
    return _BLOCK_RANGE.sub("", hblock.strip()) or None


class RowWidths:
    """Right-of-way labels (points with a width) and the lookup of the nearest one, in local metres."""

    def __init__(self, raw: dict[str, Any], scale: tuple[float, float]) -> None:
        self.scale = scale
        pts, widths = [], []
        for g, p in raw_features(raw):
            feet = metres(p.get("width"))
            if isinstance(g, shapely.Point) and feet and feet > 0:
                pts.append(self._m(g))
                widths.append(round(feet * FOOT_M, 2))
        self.widths = widths
        self.tree = STRtree(pts)

    def _m(self, g: Any) -> Any:
        sx, sy = self.scale
        return shapely.transform(g, lambda xy: xy * np.array([sx, sy]))

    def near(self, line: shapely.LineString) -> float | None:
        if not self.widths:
            return None
        i, _ = self.tree.query_nearest(self._m(line), max_distance=ROW_REACH_M, return_distance=True, all_matches=False)
        return float(self.widths[int(i[0])]) if len(i) else None


def city_streets(streets: dict[str, Any], lanes: dict[str, Any], rows: RowWidths) -> list[Feature]:
    """City centrelines; a segment published twice (same kind, same line) is kept once."""
    out: dict[str, Feature] = {}
    for raw, is_lane in ((streets, False), (lanes, True)):
        for g, p in raw_features(raw):
            kind = "lane" if is_lane else STREET_KIND.get(str(p.get("streetuse")), "residential")
            name = p.get("std_street") if is_lane else street_name(p.get("hblock"))
            parts = lines(g)
            for fid, part in zip(split_ids(shape_id(kind, g), parts), parts, strict=True):
                out.setdefault(fid, Feature(fid, part, {"kind": kind, "width_m": rows.near(part), "name": name}))
    return list(out.values())


def osm_paths_and_rail(raw: dict[str, Any]) -> list[Feature]:
    out = []
    for el in elements(raw):
        if el["type"] != "way":
            continue
        tags = el["tags"]
        kind = _osm_kind(tags)
        line = way_line(el)
        if kind is None or line is None:
            continue
        out.append(
            Feature(osm_id(el), line, {"kind": kind, "width_m": metres(tags.get("width")), "name": tags.get("name")})
        )
    return out


def _osm_kind(tags: dict[str, str]) -> str | None:
    if tags.get("tunnel") in ("yes", "building_passage") or tags.get("layer", "0").startswith("-"):
        return None
    if tags.get("railway") in RAIL:
        return "rail"
    hw = tags.get("highway")
    if hw in PATHS and tags.get("footway") not in NOT_A_PATH and tags.get("area") != "yes":
        return "path"
    return None
