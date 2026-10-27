"""What covers the ground, seen from straight above, and how high the ground is.

Both backends paint the ground from one top-down grid of surface classes: the preview looks it up per pixel, Blender
drapes it over the terrain as a texture. Drawing it once keeps the two in step and keeps polygons off the terrain mesh,
where flat street strips crumple over the hills.

Order of drawing, last wins: the area's box as plain ground, parks, sidewalks, roadways, water. Everything is clipped to
the box; outside it the class is NONE, which both backends draw black and the painter leaves transparent. Water is only
what the scene's water polygons cover.

A street's width is its right-of-way, lot line to lot line. On a street with kerbs (arterial or residential) the roadway
takes the middle and sidewalks fill the rest up to the lot line; lanes, paths and rails are drawn at
their full width.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw
from shapely.geometry import LineString, box
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry.base import BaseGeometry

from qipu_map.classes import SurfaceClass
from qipu_map.geo.boxes import WorldBox
from qipu_map.model import Polygon, Raster, Scene, StreetKind

# Each sidewalk (with its boulevard) takes this share of the right-of-way, within these bounds: a 66 ft (20 m) Vancouver
# street gets a 10 m roadway and 5 m on each side.
SIDEWALK_SHARE = 0.25
SIDEWALK_MIN_M, SIDEWALK_MAX_M = 1.5, 6.0
_STREET_CLASS = {
    StreetKind.ARTERIAL: SurfaceClass.ROAD,
    StreetKind.RESIDENTIAL: SurfaceClass.ROAD,
    StreetKind.LANE: SurfaceClass.ROAD,
    StreetKind.PATH: SurfaceClass.SIDEWALK,
    StreetKind.RAIL: SurfaceClass.RAIL,
}
_KERBED = {StreetKind.ARTERIAL, StreetKind.RESIDENTIAL}


@dataclass(frozen=True)
class GroundGrid:
    """A north-up grid of surface classes: cell (0, 0) is the north-west one, its top-left corner is (x0, y0)."""

    x0: float
    y0: float
    cell: float
    classes: NDArray[np.uint8]

    def lookup(self, x: NDArray[np.float64], y: NDArray[np.float64]) -> NDArray[np.uint8]:
        """The class under each world point; NONE outside the grid."""
        h, w = self.classes.shape
        j = np.floor((x - self.x0) / self.cell).astype(np.int64)
        i = np.floor((self.y0 - y) / self.cell).astype(np.int64)
        inside = (i >= 0) & (i < h) & (j >= 0) & (j < w)
        out = np.full(x.shape, int(SurfaceClass.NONE), dtype=np.uint8)
        out[inside] = self.classes[i[inside], j[inside]]
        return out


def snap_box(box: WorldBox, cell: float) -> WorldBox:
    """Grow a box outwards to whole cells, so grids cut from the same scene line up."""
    return WorldBox(
        math.floor(box.x0 / cell) * cell,
        math.floor(box.y0 / cell) * cell,
        math.ceil(box.x1 / cell) * cell,
        math.ceil(box.y1 / cell) * cell,
    )


def _px(points: list[tuple[float, float]], x0: float, y0: float, cell: float) -> list[tuple[float, float]]:
    # PIL puts pixel centres on whole coordinates; a cell's centre is half a cell in from its corner.
    return [((x - x0) / cell - 0.5, (y0 - y) / cell - 0.5) for x, y in points]


def _fill(img: Image.Image, shape: BaseGeometry, value: int, at: tuple[float, float, float]) -> None:
    """Fill a polygon or multipolygon on a grid whose north-west corner and cell are `at`; holes keep what was there."""
    x0, y0, cell = at
    for part in getattr(shape, "geoms", [shape]):
        if part.is_empty or not hasattr(part, "exterior"):
            continue
        outer = _px(list(part.exterior.coords), x0, y0, cell)
        if not part.interiors:
            ImageDraw.Draw(img).polygon(outer, fill=value)
            continue
        mask = Image.new("1", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.polygon(outer, fill=1)
        for hole in part.interiors:
            draw.polygon(_px(list(hole.coords), x0, y0, cell), fill=0)
        img.paste(value, mask=mask)


def _shape(p: Polygon) -> ShapelyPolygon:
    return ShapelyPolygon(p.outer, list(p.holes))


@dataclass(frozen=True)
class GroundShapes:
    """The scene's ground as filled shapes in drawing order, built once and cut into grids per frame."""

    base: SurfaceClass
    shapes: tuple[tuple[SurfaceClass, BaseGeometry], ...]


def roadway_width(kind: StreetKind, width_m: float) -> float:
    """The width of a street's paved roadway, from its right-of-way width."""
    if kind not in _KERBED:
        return width_m
    sidewalk = min(max(SIDEWALK_SHARE * width_m, SIDEWALK_MIN_M), SIDEWALK_MAX_M)
    return max(width_m - 2 * sidewalk, width_m / 3)


def ground_shapes(scene: Scene) -> GroundShapes:
    area = box(*scene.box)
    streets = [s for s in scene.streets if len(s.line) > 1 and (s.year_closed is None or s.year_closed > scene.year)]
    streets = [s for s in streets if s.year_opened is None or s.year_opened <= scene.year]
    shapes: list[tuple[SurfaceClass, BaseGeometry]] = [(SurfaceClass.GROUND, area)]
    shapes += [(SurfaceClass.GRASS, _shape(p.shape)) for p in scene.parks]
    shapes += [
        (SurfaceClass.SIDEWALK, LineString(s.line).buffer(s.width_m / 2, cap_style="flat"))
        for s in streets
        if s.kind in _KERBED
    ]
    shapes += [
        (_STREET_CLASS[s.kind], LineString(s.line).buffer(roadway_width(s.kind, s.width_m) / 2)) for s in streets
    ]
    shapes += [(SurfaceClass.WATER, _shape(p)) for p in scene.water]
    clipped = tuple((cls, shape.intersection(area)) for cls, shape in shapes)
    return GroundShapes(SurfaceClass.NONE, tuple((cls, shape) for cls, shape in clipped if not shape.is_empty))


def rasterise_ground(ground: GroundShapes, box: WorldBox, cell: float) -> GroundGrid:
    """The ground classes of `box` (x0, y0, x1, y1), `cell` metres a cell, snapped outwards to whole cells."""
    x0, y0, x1, y1 = snap_box(box, cell)
    w, h = round((x1 - x0) / cell), round((y1 - y0) / cell)
    img = Image.new("L", (w, h), int(ground.base))
    for cls, shape in ground.shapes:
        bx0, by0, bx1, by1 = shape.bounds
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        _fill(img, shape, int(cls), (x0, y1, cell))
    return GroundGrid(x0, y1, cell, np.asarray(img, dtype=np.uint8).copy())


def flat_terrain(box: WorldBox, height: float = 0.0) -> Raster:
    """A level ground, for scenes without a terrain file."""
    return Raster(
        box[0], box[3], max(box[2] - box[0], box[3] - box[1]) + 1.0, np.full((1, 1), height, dtype=np.float32)
    )
