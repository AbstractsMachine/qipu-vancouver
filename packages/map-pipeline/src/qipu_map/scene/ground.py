"""The ground plan: streets, parks, water and land, clipped to the area."""

from __future__ import annotations

from collections.abc import Iterable

import shapely

from qipu_map.geo.boxes import WorldBox
from qipu_map.model import Park, Point, Polygon, Ring, Street, StreetKind

# Curb-to-curb width when the data gives none: a Vancouver arterial has four lanes and parking, a residential street
# two lanes and parking, a lane is one truck wide. A convention, used only where the street data is silent.
DEFAULT_WIDTH_M: dict[StreetKind, float] = {
    StreetKind.ARTERIAL: 15.0,
    StreetKind.RESIDENTIAL: 9.0,
    StreetKind.LANE: 6.0,
    StreetKind.PATH: 3.0,
    StreetKind.RAIL: 4.0,
}
MIN_PIECE_M2 = 1.0  # clipping leaves crumbs along the box's edge


def street(sid: str, line: Iterable[Point], kind: str, width_m: float | None, name: str | None) -> Street:
    k = StreetKind(kind)
    width = width_m if width_m and width_m > 0 else DEFAULT_WIDTH_M[k]
    return Street(sid, tuple((round(x, 3), round(y, 3)) for x, y in line), round(width, 2), k, name)


def clip_lines(streets: list[Street], box: WorldBox) -> list[Street]:
    """Streets cut to the box (with a street's width of margin, so a curb at the edge is still drawn)."""
    out = []
    for s in streets:
        area = box.shape().buffer(s.width_m, join_style="mitre")
        cut = shapely.LineString(s.line).intersection(area)
        for k, part in enumerate(
            p for p in shapely.get_parts(cut) if isinstance(p, shapely.LineString) and p.length > 0
        ):
            line = tuple((float(x), float(y)) for x, y in shapely.get_coordinates(part))
            out.append(Street(s.id if k == 0 else f"{s.id}-{k}", line, s.width_m, s.kind, s.name))
    return sorted(out, key=lambda s: s.id)


def to_polygons(g: shapely.Geometry) -> tuple[Polygon, ...]:
    """Every polygon part of a geometry, outer rings counter-clockwise and holes clockwise, rings left open."""
    parts = [
        p
        for p in shapely.get_parts(shapely.orient_polygons(g))
        if isinstance(p, shapely.Polygon) and p.area >= MIN_PIECE_M2
    ]
    return tuple(Polygon(_ring(p.exterior), tuple(_ring(h) for h in p.interiors)) for p in sorted(parts, key=_order))


def parks(items: list[tuple[str, shapely.Polygon | shapely.MultiPolygon, str | None]], box: WorldBox) -> list[Park]:
    area = box.shape()
    out = []
    for pid, shape, name in sorted(items, key=lambda t: t[0]):
        for k, piece in enumerate(to_polygons(shape.intersection(area))):
            out.append(Park(pid if k == 0 else f"{pid}-{k}", piece, name))
    return out


def water_and_land(
    water: list[shapely.Polygon | shapely.MultiPolygon], box: WorldBox
) -> tuple[tuple[Polygon, ...], tuple[Polygon, ...]]:
    """The water inside the box, and the land: the box minus the water."""
    area = box.shape()
    wet = shapely.union_all([shapely.make_valid(w) for w in water]).intersection(area) if water else shapely.Polygon()
    return to_polygons(wet), to_polygons(area.difference(wet))


def _ring(r: shapely.LinearRing) -> Ring:
    return tuple((round(float(x), 3), round(float(y), 3)) for x, y in shapely.get_coordinates(r)[:-1])


def _order(p: shapely.Polygon) -> tuple[float, float]:
    b = p.bounds
    return (b[0], b[1])
