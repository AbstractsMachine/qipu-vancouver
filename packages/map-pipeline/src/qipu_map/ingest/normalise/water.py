"""Water: the sea cut out of the box along the shoreline, and the lakes, ponds and rivers OSM maps.

The City's 2002 shoreline is the line drawn, but it is a bare line: it does not say which side is water.
OSM's coastline does, by convention (land on the left of the way's direction, sea on the right). So the box is cut
along the City's line and each piece is called sea or land by the side of the nearest OSM coastline it lies on.
Where the City has no shoreline in the box, the OSM coastline does both jobs.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

import shapely
from shapely.ops import polygonize, unary_union

from qipu_map.ingest.normalise.geojson import Feature, lines, polygons, raw_features, split_ids
from qipu_map.ingest.normalise.osm import area_shape, elements, osm_id, way_line

LAKES = frozenset({"lake", "reservoir", "lagoon"})
RIVERS = frozenset({"river", "canal", "stream", "oxbow"})


def coastlines(raw_osm: dict[str, Any]) -> list[shapely.LineString]:
    out = []
    for el in elements(raw_osm):
        line = way_line(el) if el["type"] == "way" and el["tags"].get("natural") == "coastline" else None
        if line is not None:
            out.append(line)
    return out


Segment = tuple[tuple[float, float], tuple[float, float]]


def sea_side(point: shapely.Point, coast: Sequence[shapely.LineString]) -> bool:
    """True when the point lies to the right of the nearest coastline, the sea side.

    Where the nearest place on the coast is a corner (two segments, of one way or of two ways that meet), each segment
    alone can give the wrong side. At a left turn the sea is the wide side: right of either segment is sea. At a right
    turn it is the narrow wedge: the point must be right of both.
    """
    segs: list[Segment] = [
        ((ax, ay), (bx, by)) for line in coast for (ax, ay), (bx, by) in itertools.pairwise(line.coords)
    ]
    if not segs:
        return False
    dists = [shapely.LineString(seg).distance(point) for seg in segs]
    nearest = min(dists)
    tied = [seg for seg, d in zip(segs, dists, strict=True) if d <= nearest + 1e-9]
    p = (point.x, point.y)
    if len(tied) == 2:
        first, second = tied if tied[0][1] == tied[1][0] else tied[::-1]
        corner = first[1]
        if corner == second[0] and math.dist(corner, p) <= nearest + 1e-9:
            right = (_cross(*first, p) < 0, _cross(*second, p) < 0)
            turns_left = _cross(first[0], corner, second[1]) > 0
            return any(right) if turns_left else all(right)
    return _cross(*tied[0], p) < 0


def _cross(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> float:
    """Positive when p is left of the line from a to b, negative when right."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def sea(
    clip: shapely.Polygon, shoreline: Sequence[shapely.LineString], coast: Sequence[shapely.LineString]
) -> list[shapely.Polygon]:
    """The pieces of the box on the sea side of the shore."""
    if not coast:
        return []
    cutter = unary_union(list(shoreline)).intersection(clip) if shoreline else shapely.LineString()
    if cutter.is_empty:
        cutter = unary_union(list(coast)).intersection(clip)
    noded = unary_union([clip.exterior, cutter])
    faces = [f for f in polygonize(lines(noded)) if f.area > 0]
    pieces = [f for f in faces if sea_side(f.representative_point(), coast)]
    return polygons(unary_union(pieces)) if pieces else []


def inland(raw_osm: dict[str, Any], clip: shapely.Polygon) -> list[Feature]:
    """Lakes, ponds and rivers OSM maps as areas, cut to the box."""
    out = []
    for el in elements(raw_osm):
        tags = el["tags"]
        if tags.get("natural") != "water" and tags.get("waterway") != "riverbank":
            continue
        g = area_shape(el)
        parts = polygons(g.intersection(clip)) if g is not None else []
        kind = (
            "river"
            if tags.get("waterway") == "riverbank" or tags.get("water") in RIVERS
            else "lake"
            if tags.get("water") in LAKES
            else "pond"
        )
        for fid, part in zip(split_ids(osm_id(el), parts), parts, strict=True):
            out.append(Feature(fid, part, {"kind": kind}))
    return out


def water(shoreline_raw: dict[str, Any], raw_osm: dict[str, Any], clip: shapely.Polygon) -> list[Feature]:
    shore = [part for g, _ in raw_features(shoreline_raw) for part in lines(g)]
    seas = sea(clip, shore, coastlines(raw_osm))
    out = [Feature(fid, p, {"kind": "sea"}) for fid, p in zip(split_ids("sea", seas), seas, strict=True)]
    return out + inland(raw_osm, clip)
