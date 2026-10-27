"""A building's massing: the closed mesh of its walls, roof and floor.

This is the shape the renderer draws, in Blender and in the preview rasteriser alike. Walls stand on the footprint from
the ground to the eave, a flat roof caps the footprint at the top, and a pitched roof is a height field over the
footprint. The roof's axes come from the footprint's minimum-area rectangle; a gable rises linearly from both long eaves
to a ridge, a hip from all four sides. Gable ends and hip ends follow the roof, so every wall is one convex face that
reaches the roof line.

Heights: `ground_m` is the building's ground and `height_m` the top of the building above it (the ridge, for a pitched
roof). The walls start `FOOT_M` below the ground, so a gentle slope never shows a gap under them. Faces run
counter-clockwise seen from outside. Roofs and the floor are triangles, walls are one polygon per footprint edge.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass
from qipu_map.model import Building, BuildingType, Point, Ring, RoofForm, ccw, signed_area

# The roof pitch each type gets, in degrees. The LiDAR's own pitch is not kept: at 1 m cells it is too noisy for a
# house.
PITCH_DEG: dict[BuildingType, float] = {
    BuildingType.CHARACTER_HOUSE: 42.0,
    BuildingType.VANCOUVER_SPECIAL: 16.0,
    BuildingType.MODERN_HOUSE: 28.0,
    BuildingType.LANEWAY_HOUSE: 32.0,
    BuildingType.ROW_HOUSE: 30.0,
    BuildingType.WALK_UP: 26.0,
    BuildingType.CIVIC: 30.0,
    BuildingType.SHED: 22.0,
    BuildingType.INDUSTRIAL: 16.0,
}
DEFAULT_PITCH_DEG = 28.0

# Pitched roofs only on small, low buildings: on anything bigger a gable reads as a barn.
MAX_PITCHED_AREA_M2 = 800.0
MAX_PITCHED_HEIGHT_M = 25.0
# A roof never takes more than this share of the building's height, so a steep roof on a wide house keeps its walls.
MAX_RISE_SHARE = 0.55
# Walls run 0.6 m into the ground below the building's lowest corner, so a slope never shows a gap under them.
FOOT_M = 0.6
_EPS = 1e-9

Vec3 = tuple[float, float, float]
Plane = Callable[[Point], float]


@dataclass(frozen=True)
class Mesh:
    vertices: NDArray[np.float64]  # (n, 3) world metres
    faces: tuple[tuple[int, ...], ...]  # counter-clockwise seen from outside
    face_class: tuple[SurfaceClass, ...]  # ROOF or WALL per face (the floor counts as WALL)


@dataclass(frozen=True)
class RoofShape:
    """A roof as a height function over the footprint, and the crease lines where its slope changes."""

    height: Plane
    creases: tuple[Plane, ...]


def building_mesh(b: Building) -> Mesh:
    """The closed mesh of a building: roof, one wall per footprint edge, and a floor, in world metres."""
    ring = ccw(b.footprint)
    shape = roof_shape(b, ring)
    builder = _MeshBuilder()
    foot = b.ground_m - FOOT_M
    for tri in _triangles(ring):
        for part in _split_all(tri, shape.creases):
            builder.face([(x, y, shape.height((x, y))) for x, y in part], SurfaceClass.ROOF)
    for a, c in zip(ring, ring[1:] + ring[:1], strict=True):
        top = _split_segment(a, c, shape.creases)
        wall = [(a[0], a[1], foot), (c[0], c[1], foot)]
        wall += [(x, y, shape.height((x, y))) for x, y in reversed(top)]
        builder.face(wall, SurfaceClass.WALL)
    for tri in _triangles(ring):
        builder.face([(x, y, foot) for x, y in reversed(tri)], SurfaceClass.WALL)
    return builder.mesh()


def roof_shape(b: Building, ring: Ring) -> RoofShape:
    """The roof's height function. Big or tall buildings, and buildings too low to pitch, get a flat roof."""
    top = b.ground_m + b.height_m
    area = abs(signed_area(ring))
    if b.roof is RoofForm.FLAT or area > MAX_PITCHED_AREA_M2 or b.height_m >= MAX_PITCHED_HEIGHT_M:
        return RoofShape(lambda _p: top, ())
    origin, along, across = _axes(ring, ridge_across=b.kind is BuildingType.VANCOUVER_SPECIAL)

    def coords(p: Point) -> tuple[float, float]:
        dx, dy = p[0] - origin[0], p[1] - origin[1]
        return dx * along[0] + dy * along[1], dx * across[0] + dy * across[1]

    vs, us = zip(*(coords(p) for p in ring), strict=True)
    vmin, vmax, umin, umax = min(vs), max(vs), min(us), max(us)
    half_across, half_along = (umax - umin) / 2, (vmax - vmin) / 2
    tan = math.tan(math.radians(PITCH_DEG.get(b.kind, DEFAULT_PITCH_DEG)))
    reach = half_across if b.roof is RoofForm.GABLE else min(half_across, half_along)
    rise = min(reach * tan, MAX_RISE_SHARE * b.height_m)
    if reach < 0.5 or rise < 0.1:
        return RoofShape(lambda _p: top, ())
    slope, eave = rise / reach, top - rise

    if b.roof is RoofForm.GABLE:
        uc = (umin + umax) / 2
        return RoofShape(
            lambda p: eave + slope * (half_across - abs(coords(p)[1] - uc)), (lambda p: coords(p)[1] - uc,)
        )

    def hip(p: Point) -> float:
        v, u = coords(p)
        return float(eave + slope * max(0.0, min(u - umin, umax - u, v - vmin, vmax - v)))

    creases: tuple[Plane, ...] = (
        lambda p: (coords(p)[1] - umin) - (coords(p)[0] - vmin),
        lambda p: (coords(p)[1] - umin) - (vmax - coords(p)[0]),
        lambda p: (umax - coords(p)[1]) - (coords(p)[0] - vmin),
        lambda p: (umax - coords(p)[1]) - (vmax - coords(p)[0]),
        lambda p: coords(p)[1] - (umin + umax) / 2,
    )
    return RoofShape(hip, creases)


def _axes(ring: Ring, *, ridge_across: bool) -> tuple[Point, Point, Point]:
    """An origin and two unit vectors: `along` the ridge and `across` it.

    The ridge runs along the rectangle's long side, as on a front-gabled house on a deep lot; with `ridge_across` it
    runs along the short side, as on a Vancouver Special, whose side gable faces the neighbours.
    """
    with np.errstate(divide="ignore", invalid="ignore"):  # GEOS divides by zero on an axis-aligned ring, harmlessly
        rect = shapely.minimum_rotated_rectangle(shapely.Polygon(ring))
    c = shapely.get_coordinates(rect)[:4].tolist()
    first, second = (c[1][0] - c[0][0], c[1][1] - c[0][1]), (c[2][0] - c[1][0], c[2][1] - c[1][1])
    sides = sorted((first, second), key=lambda s: -math.hypot(*s))
    along = _unit(sides[1] if ridge_across else sides[0])
    return (c[0][0], c[0][1]), along, (-along[1], along[0])


def _unit(v: Point) -> Point:
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n)


def _triangles(ring: Ring) -> list[tuple[Point, Point, Point]]:
    """The footprint cut into triangles on its own vertices, each counter-clockwise."""
    out = []
    tris = shapely.constrained_delaunay_triangles(shapely.Polygon(ring))
    for t in shapely.get_parts(tris):
        a, b, c = ((float(x), float(y)) for x, y in shapely.get_coordinates(t)[:3].tolist())
        out.append((a, b, c) if signed_area((a, b, c)) > 0 else (a, c, b))
    out.sort()
    return out


def _cross(a: Point, b: Point, f: Plane) -> Point:
    """Where the crease f = 0 crosses the segment ab, computed the same way whichever way the segment runs."""
    p, q = (a, b) if a <= b else (b, a)
    fp, fq = f(p), f(q)
    t = float(fp / (fp - fq))
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def _side(v: float) -> int:
    return 0 if abs(v) < _EPS else (1 if v > 0 else -1)


def _split(poly: tuple[Point, ...], f: Plane) -> list[tuple[Point, ...]]:
    """Cut a convex polygon along the crease f = 0 into its two sides, then fan each side into triangles."""
    sides = [_side(f(p)) for p in poly]
    if all(s >= 0 for s in sides) or all(s <= 0 for s in sides):
        return [poly]
    pos: list[Point] = []
    neg: list[Point] = []
    for i, p in enumerate(poly):
        q, sp, sq = poly[(i + 1) % len(poly)], sides[i], sides[(i + 1) % len(poly)]
        if sp >= 0:
            pos.append(p)
        if sp <= 0:
            neg.append(p)
        if sp * sq < 0:
            x = _cross(p, q, f)
            pos.append(x)
            neg.append(x)
    return [tuple(part[:1] + part[k : k + 2]) for part in (pos, neg) for k in range(1, len(part) - 1)]


def _split_all(tri: tuple[Point, ...], creases: tuple[Plane, ...]) -> list[tuple[Point, ...]]:
    parts = [tri]
    for f in creases:
        parts = [q for p in parts for q in _split(p, f)]
    return parts


def _split_segment(a: Point, c: Point, creases: tuple[Plane, ...]) -> list[Point]:
    """The points along a footprint edge where the roof line bends, ends included, in order from a to c."""
    points = [a, c]
    for f in creases:
        nxt = [points[0]]
        for p, q in itertools.pairwise(points):
            if _side(f(p)) * _side(f(q)) < 0:
                nxt.append(_cross(p, q, f))
            nxt.append(q)
        points = nxt
    return points


class _MeshBuilder:
    """Collects faces and shares vertices between them, so the mesh is closed."""

    def __init__(self) -> None:
        self._index: dict[Vec3, int] = {}
        self._faces: list[tuple[int, ...]] = []
        self._classes: list[SurfaceClass] = []

    def face(self, points: list[Vec3], cls: SurfaceClass) -> None:
        ids: list[int] = []
        for p in points:
            i = self._index.setdefault(p, len(self._index))
            if not ids or ids[-1] != i:
                ids.append(i)
        if len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        if len(ids) >= 3:
            self._faces.append(tuple(ids))
            self._classes.append(cls)

    def mesh(self) -> Mesh:
        vertices = np.array(list(self._index), dtype=np.float64).reshape(-1, 3)
        return Mesh(vertices, tuple(self._faces), tuple(self._classes))
