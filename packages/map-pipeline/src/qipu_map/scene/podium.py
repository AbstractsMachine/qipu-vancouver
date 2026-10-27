"""A tower standing on a podium inside one outline: find the tower's own outline in the LiDAR.

The City traced one footprint for a tower and its podium. Extruded to the median, the tower vanishes; extruded to the
tower's height, the podium becomes a slab the size of a block (St Paul's Hospital stood 44 m tall over 2 ha). Such
records are split in two: the tower is the cells that stand above halfway between the podium (the median) and the tower
top (the 90th percentile), drawn as one simplified outline.
"""

from __future__ import annotations

import numpy as np
import shapely

from qipu_map.model import Raster
from qipu_map.scene.pixels import inside, window

MIN_TOWER_M2 = 60.0
SIMPLIFY_M = 1.0


def tower_outline(
    footprint: shapely.Polygon, dsm: Raster, dem: Raster, podium_m: float, top_m: float
) -> shapely.Polygon | None:
    """The tower's outline inside the footprint, or None when no single tower stands out of it."""
    if not dsm.same_grid(dem):
        raise ValueError("the DSM and DEM must be on one grid")
    top, ground = window(dsm, footprint.bounds), window(dem, footprint.bounds)
    if top.values.size == 0:
        return None
    above = np.nan_to_num(top.values - ground.values, nan=0.0)
    cells = inside(top, footprint) & (above >= (podium_m + top_m) / 2)
    if not cells.any():
        return None
    gx, gy = top.centres()
    half = top.cell / 2
    squares = shapely.box(gx[cells] - half, gy[cells] - half, gx[cells] + half, gy[cells] + half)
    merged = shapely.union_all(squares).simplify(SIMPLIFY_M).intersection(footprint)
    parts = [p for p in shapely.get_parts(merged) if isinstance(p, shapely.Polygon)]
    if not parts:
        return None
    tower = shapely.Polygon(max(parts, key=lambda p: p.area).exterior)
    if tower.area < MIN_TOWER_M2:
        return None
    oriented: shapely.Polygon = shapely.orient_polygons(tower)
    return oriented
