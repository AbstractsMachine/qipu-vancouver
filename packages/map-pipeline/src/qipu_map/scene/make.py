"""Today's scene for one area, from the ingest folder."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.errors import StageError
from qipu_map.geo.boxes import WorldBox
from qipu_map.geo.projection import LocalProjection
from qipu_map.model import Raster, Scene
from qipu_map.scene import ground, inputs, trees
from qipu_map.scene.buildings import Footprint, build_all
from qipu_map.scene.pixels import inside, window

log = logging.getLogger(__name__)
TERRAIN_FILE = "terrain.npz"


@dataclass(frozen=True)
class SceneArea:
    """The city, area name, year, world box (metres) and projection a scene is made for."""

    city: str
    name: str
    year: int
    box: WorldBox
    projection: LocalProjection


def make_scene(ingest: Path, area: SceneArea) -> tuple[Scene, Raster]:
    """The scene and its terrain. Pure apart from reading the ingest files."""
    proj, box = area.projection, area.box
    dsm, dem = Raster.load(ingest / "dsm.npz"), Raster.load(ingest / "dem.npz")
    if not dsm.same_grid(dem):
        raise StageError(f"dsm.npz and dem.npz in {ingest} are on different grids: run `qipu-map ingest` again")
    fps = inputs.footprints(ingest / "buildings.geojson", proj, box)
    buildings, notes = build_all(fps, dsm, dem)
    log.info("%d buildings (%d footprints)", len(buildings), len(fps))

    listed = [trees.street_tree(t) for t in inputs.listed_trees(ingest / "trees.geojson", proj, box)]
    above = _height_above_ground(dsm, dem, box)
    crowns = trees.canopy(above, _on_buildings(above, fps), listed)
    log.info("%d street trees, %d canopy crowns", len(listed), len(crowns))

    streets = ground.clip_lines(
        [
            ground.street(str(p["id"]), shapely.get_coordinates(g).tolist(), p["kind"], p.get("width_m"), p.get("name"))
            for g, p in inputs.features(ingest / "streets.geojson", proj)
            if isinstance(g, shapely.LineString)
        ],
        box,
    )
    parks = ground.parks(
        [
            (str(p["id"]), g, p.get("name"))
            for g, p in inputs.features(ingest / "parks.geojson", proj)
            if isinstance(g, shapely.Polygon | shapely.MultiPolygon)
        ],
        box,
    )
    water, land = ground.water_and_land(
        [
            g
            for g, _ in inputs.features(ingest / "water.geojson", proj)
            if isinstance(g, shapely.Polygon | shapely.MultiPolygon)
        ],
        box,
    )

    terrain = dem.crop(box)
    terrain = Raster(terrain.x0, terrain.y0, terrain.cell, np.nan_to_num(terrain.data, nan=0.0).astype(np.float32))
    notes["trees"] = {"street": len(listed), "canopy": len(crowns)}
    scene = Scene(
        city=area.city,
        area=area.name,
        year=area.year,
        box=box,
        buildings=tuple(buildings),
        streets=tuple(streets),
        trees=tuple(sorted(listed + crowns, key=lambda t: t.id)),
        parks=tuple(parks),
        water=water,
        land=land,
        terrain_file=TERRAIN_FILE,
        notes=notes,
    )
    return scene, terrain


def _height_above_ground(dsm: Raster, dem: Raster, box: WorldBox) -> Raster:
    top, bottom = dsm.crop(box), dem.crop(box)
    return Raster(top.x0, top.y0, top.cell, (top.data - bottom.data).astype(np.float32))


def _on_buildings(grid: Raster, fps: list[Footprint]) -> NDArray[np.bool_]:
    """The grid's cells on a footprint, grown by one cell (walls and eaves read half tree, half roof)."""
    mask = np.zeros(grid.data.shape, dtype=bool)
    for fp in fps:
        win = window(grid, fp.outline.buffer(grid.cell).bounds)
        if win.values.size:
            h, w = win.values.shape
            mask[win.i0 : win.i0 + h, win.j0 : win.j0 + w] |= inside(win, fp.outline.buffer(grid.cell))
    return mask
