"""Small scenes and a box mesher for the render tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass
from qipu_map.geo.boxes import WorldBox
from qipu_map.geo.camera import ObliqueCamera
from qipu_map.model import (
    Building,
    BuildingType,
    Park,
    Polygon,
    Raster,
    RoofForm,
    Scene,
    Street,
    StreetKind,
    Tree,
    TreeForm,
    YearSource,
)

CAMERA = ObliqueCamera(azimuth_deg=0.0, elevation_deg=30.709, metres_per_px=0.5)


@dataclass(frozen=True)
class BoxMesh:
    vertices: NDArray[np.float64]
    faces: tuple[tuple[int, ...], ...]
    face_class: tuple[SurfaceClass, ...]


def box_mesh(b: Building) -> BoxMesh:
    """A flat-topped prism on an axis-aligned rectangle (the footprint's bounding box)."""
    xs, ys = [p[0] for p in b.footprint], [p[1] for p in b.footprint]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    z0, z1 = b.ground_m, b.ground_m + b.height_m
    ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    verts = [(x, y, z0) for x, y in ring] + [(x, y, z1) for x, y in ring]
    faces: list[tuple[int, ...]] = [(4, 5, 6, 7)]
    faces += [(i, (i + 1) % 4, (i + 1) % 4 + 4, i + 4) for i in range(4)]
    faces.append((3, 2, 1, 0))
    classes = (SurfaceClass.ROOF,) + (SurfaceClass.WALL,) * 5
    return BoxMesh(np.array(verts, dtype=np.float64), tuple(faces), classes)


def building(bid: str, box: tuple[float, float, float, float], height: float, *, year: int | None = 1990) -> Building:
    x0, y0, x1, y1 = box
    return Building(
        id=bid,
        footprint=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
        ground_m=0.0,
        height_m=height,
        roof=RoofForm.FLAT,
        kind=BuildingType.MID_RISE,
        year_built=year,
        year_source=YearSource.TAX_ROLL,
    )


def small_scene(
    buildings: tuple[Building, ...] | None = None, *, year: int = 2026, ground: Mapping[str, Any] | None = None
) -> Scene:
    """Two buildings, a street, a tree, a park and a pond; `ground` replaces the streets, trees, parks, water or
    land."""
    blds = (
        buildings
        if buildings is not None
        else (building("a", (20, 20, 40, 30), 12), building("b", (60, 50, 70, 60), 30))
    )
    scene = Scene(
        city="test",
        area="test",
        year=year,
        box=WorldBox(0.0, 0.0, 100.0, 100.0),
        buildings=blds,
        streets=(Street("s1", ((0.0, 10.0), (100.0, 10.0)), 8.0, StreetKind.RESIDENTIAL),),
        trees=(Tree("t1", 80.0, 20.0, 10.0, 6.0, TreeForm.BROADLEAF),),
        parks=(Park("p1", Polygon(((70.0, 70.0), (95.0, 70.0), (95.0, 95.0), (70.0, 95.0)))),),
        water=(Polygon(((0.0, 80.0), (30.0, 80.0), (30.0, 100.0), (0.0, 100.0))),),
        land=(),
        terrain_file="terrain.npz",
    )
    return replace(scene, **(ground or {}))


def flat(height: float = 0.0) -> Raster:
    return Raster(-200.0, 400.0, 2.0, np.full((300, 300), height, dtype=np.float32))


def slope() -> Raster:
    """Ground rising 1 m every 10 m northwards."""
    rows = np.arange(300, dtype=np.float32)
    y = 400.0 - (rows + 0.5) * 2.0
    return Raster(-200.0, 400.0, 2.0, np.repeat((y / 10.0)[:, None], 300, axis=1).astype(np.float32))
