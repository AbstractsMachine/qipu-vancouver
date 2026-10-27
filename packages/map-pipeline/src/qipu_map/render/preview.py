"""The preview renderer: the scene through the map's camera in plain Python, no Blender.

It draws what Blender draws and puts it in the same place (both go through `geo.camera.Canvas`), with none of the
light: the ground is looked up per pixel, then building faces and tree crowns are filled far to near (a painter's
algorithm), shaded flat by the sun. CI and the bundled sample use it, and the tests check the camera math against it.

Known limits, all fine for a preview: no cast shadows, no windows, hills do not hide the buildings behind them, and
tree crowns are discs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from qipu_map.classes import SurfaceClass
from qipu_map.geo.boxes import WorldBox
from qipu_map.geo.camera import Canvas
from qipu_map.model import Raster, Scene
from qipu_map.render.frames import Frame
from qipu_map.render.ground import GroundShapes, ground_shapes, rasterise_ground
from qipu_map.render.look import GROUND, Colour, Light, building_look
from qipu_map.render.meshes import Mesher, face_normal
from qipu_map.render.passes import id_colour

AMBIENT = 0.55
# Each round shrinks the error by the slope times cot(elevation): 0.17 on a 10 % street, so eight rounds are plenty.
_GROUND_HIT_ROUNDS = 8

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Shape:
    """One thing to fill: a polygon or a disc in canvas pixels, with its value in each pass."""

    depth: float
    points: tuple[tuple[float, float], ...]
    disc: tuple[float, float, float] | None
    colour: tuple[int, int, int]
    surface: int
    building: tuple[int, int, int]
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class Passes:
    beauty: NDArray[np.uint8]
    classes: NDArray[np.uint8]
    ids: NDArray[np.uint8]


def sun_vector(light: Light) -> Vec:
    a, e = math.radians(light.sun_azimuth_deg), math.radians(light.sun_elevation_deg)
    return (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))


def shade(rgb: Colour, n_dot_sun: float, light: Light) -> tuple[int, int, int]:
    """Flat Lambert, scaled so level ground in full sun keeps its palette colour."""
    flat = AMBIENT + (1 - AMBIENT) * math.sin(math.radians(light.sun_elevation_deg))
    k = (AMBIENT + (1 - AMBIENT) * max(0.0, n_dot_sun)) / flat
    r, g, b = (min(255, round(c * k * 255)) for c in rgb)
    return (r, g, b)


def _dot(a: Vec, b: NDArray[np.float64]) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def scene_shapes(scene: Scene, canvas: Canvas, terrain: Raster, mesher: Mesher, light: Light) -> list[Shape]:
    """Every building face that faces the camera and every tree crown, sorted far to near."""
    fwd, sun = canvas.camera.forward, sun_vector(light)
    shapes: list[Shape] = []
    for index, b in enumerate(scene.buildings):
        if not b.stands_in(scene.year):
            continue
        mesh, look, bid = mesher(b), building_look(b), id_colour(index)
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        px = canvas.to_px_array(verts)
        # One depth per building, so its faces stay together: the painter's order is between buildings.
        depth = _dot(fwd, verts.mean(axis=0))
        faces = []
        for face, cls in zip(mesh.faces, mesh.face_class, strict=True):
            idx = list(face)
            n = face_normal(verts[idx])
            if _dot(fwd, n) >= 0:
                continue
            rgb = look.roof if cls == SurfaceClass.ROOF else look.wall
            pts = tuple((float(px[i, 0]), float(px[i, 1])) for i in idx)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            faces.append((_dot(fwd, verts[idx].mean(axis=0)), pts, shade(rgb, _dot(sun, n), light), int(cls), (xs, ys)))
        for face_depth, pts, colour, surface, (xs, ys) in sorted(faces, key=lambda f: -f[0]):
            bounds = (min(xs), min(ys), max(xs), max(ys))
            shapes.append(Shape(depth + face_depth * 1e-6, pts, None, colour, surface, bid, bounds))
    tree_colour = shade(GROUND[SurfaceClass.TREE], 1.0, light)
    for t in scene.trees:
        if t.year_planted is not None and t.year_planted > scene.year:
            continue
        ground = terrain.value_at(t.x, t.y)
        z = ground + max(t.height_m - t.crown_m / 2, t.crown_m / 2)
        cx, cy = canvas.to_px(t.x, t.y, z)
        r = t.crown_m / 2 / canvas.camera.metres_per_px
        depth = _dot(fwd, np.array([t.x, t.y, z]))
        bounds = (cx - r, cy - r, cx + r, cy + r)
        shapes.append(Shape(depth, (), (cx, cy, r), tree_colour, int(SurfaceClass.TREE), (0, 0, 0), bounds))
    return sorted(shapes, key=lambda s: -s.depth)


def ground_points(canvas: Canvas, frame: Frame, terrain: Raster) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """The world (x, y) of the ground each pixel of the frame shows, its centre's ray walked onto the terrain."""
    cam, m = canvas.camera, canvas.camera.metres_per_px
    u = np.arange(frame.w, dtype=np.float64) + frame.x + 0.5
    v = np.arange(frame.h, dtype=np.float64) + frame.y + 0.5
    sx, sy = np.meshgrid(canvas.left + u * m, canvas.top - v * m)
    z = np.zeros_like(sx)
    for _ in range(_GROUND_HIT_ROUNDS):
        x, y = cam.ground_from_screen_array(sx, sy, z)
        z = terrain.sample(x, y)
    return x, y


def _ground_shading(
    terrain: Raster, x: NDArray[np.float64], y: NDArray[np.float64], light: Light
) -> NDArray[np.float64]:
    d = terrain.cell
    gx = (terrain.sample(x + d, y) - terrain.sample(x - d, y)) / (2 * d)
    gy = (terrain.sample(x, y + d) - terrain.sample(x, y - d)) / (2 * d)
    n = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    ndl = np.clip(n @ np.array(sun_vector(light)), 0.0, None)
    flat = AMBIENT + (1 - AMBIENT) * math.sin(math.radians(light.sun_elevation_deg))
    out: NDArray[np.float64] = (AMBIENT + (1 - AMBIENT) * ndl) / flat
    return out


@dataclass(frozen=True)
class PreviewScene:
    """A scene made ready for the preview: drawn once, then cut into any number of frames."""

    canvas: Canvas
    terrain: Raster
    ground: GroundShapes
    shapes: tuple[Shape, ...]
    light: Light

    @classmethod
    def build(cls, scene: Scene, canvas: Canvas, terrain: Raster, mesher: Mesher, light: Light) -> PreviewScene:
        shapes = tuple(scene_shapes(scene, canvas, terrain, mesher, light))
        return cls(canvas, terrain, ground_shapes(scene), shapes, light)

    def render(self, frame: Frame) -> Passes:
        base = self._ground(frame)
        images = (
            Image.fromarray(base.beauty, "RGB"),
            Image.fromarray(base.classes, "L"),
            Image.fromarray(base.ids, "RGB"),
        )
        draws = [ImageDraw.Draw(im) for im in images]
        # PIL puts pixel centres on whole coordinates; canvas pixel i spans [i, i + 1), so shift by half a pixel.
        ox, oy = frame.x + 0.5, frame.y + 0.5
        for s in self.shapes:
            x0, y0, x1, y1 = s.bounds
            if x1 < frame.x or y1 < frame.y or x0 > frame.x + frame.w or y0 > frame.y + frame.h:
                continue
            values: tuple[tuple[int, ...] | int, ...] = (s.colour, s.surface, s.building)
            if s.disc is not None:
                cx, cy, r = s.disc
                box = (cx - ox - r, cy - oy - r, cx - ox + r, cy - oy + r)
                for draw, value in zip(draws, values, strict=True):
                    draw.ellipse(box, fill=value)
            else:
                pts = [(px - ox, py - oy) for px, py in s.points]
                for draw, value in zip(draws, values, strict=True):
                    draw.polygon(pts, fill=value)
        return Passes(*(np.asarray(im, dtype=np.uint8) for im in images))

    def _ground(self, frame: Frame) -> Passes:
        x, y = ground_points(self.canvas, frame, self.terrain)
        cell = self.canvas.camera.metres_per_px
        box = WorldBox(float(np.min(x)), float(np.min(y)), float(np.max(x)), float(np.max(y)))
        grid = rasterise_ground(self.ground, box, cell)
        classes = grid.lookup(x, y)
        lut = np.zeros((256, 3), dtype=np.float64)
        for c, rgb in GROUND.items():
            lut[int(c)] = rgb
        k = _ground_shading(self.terrain, x, y, self.light)[..., None]
        beauty = np.clip(np.rint(lut[classes] * k * 255), 0, 255).astype(np.uint8)
        return Passes(beauty, classes, np.zeros((frame.h, frame.w, 3), dtype=np.uint8))
