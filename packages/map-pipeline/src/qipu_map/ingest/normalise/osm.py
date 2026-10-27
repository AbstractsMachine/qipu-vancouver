"""OpenStreetMap elements (Overpass JSON with `out tags geom`) to shapes, and the tag readers the layers share."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from qipu_map.values import year_in

Element = dict[str, Any]

_NUMBER = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(m|metres|meters|ft|feet|')?")
YEAR_TAGS = ("start_date", "construction_date", "building:start_date", "opening_date", "year_built")


def elements(raw: dict[str, Any]) -> Iterator[Element]:
    """Elements with tags, in a stable order."""
    for el in sorted(raw.get("elements", []), key=lambda e: (e["type"], e["id"])):
        if el.get("tags"):
            yield el


def osm_id(el: Element) -> str:
    """The layer id of an OSM element: `osm-` plus the first letter of its type and its number, such as `osm-w123`."""
    return f"osm-{el['type'][0]}{el['id']}"


def way_line(el: Element) -> shapely.LineString | None:
    """The way's geometry as a line string in degrees, or None when it has fewer than two points."""
    pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]
    return shapely.LineString(pts) if len(pts) >= 2 else None


def area_shape(el: Element) -> BaseGeometry | None:
    """A closed way's polygon, or a multipolygon relation's outers minus its inners. None when it does not close."""
    if el["type"] == "way":
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]
        if len(pts) < 4 or pts[0] != pts[-1]:
            return None
        return shapely.make_valid(shapely.Polygon(pts))
    outers: list[shapely.LineString] = []
    inners: list[shapely.LineString] = []
    for m in el.get("members", []):
        line = way_line(m) if m.get("type") == "way" else None
        if line is not None:
            (inners if m.get("role") == "inner" else outers).append(line)
    shell = unary_union(list(polygonize(outers)))
    if shell.is_empty:
        return None
    holes = unary_union(list(polygonize(inners)))
    return shapely.make_valid(shell.difference(holes) if not holes.is_empty else shell)


def metres(value: str | None) -> float | None:
    """'45', '45 m', '45.5m', "150'", '150 ft' to metres; None when it is not a number."""
    if value is None:
        return None
    m = _NUMBER.match(str(value).strip().lower().replace(",", "."))
    if not m:
        return None
    x = float(m.group(1))
    return x * 0.3048 if m.group(2) in ("ft", "feet", "'") else x


def year_of(tags: dict[str, str]) -> int | None:
    """The first four-digit year in the first date tag that has one."""
    return next((y for key in YEAR_TAGS if (y := year_in(tags.get(key))) is not None), None)
