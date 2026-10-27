"""ground.json: a coarse grid of ground heights, so the viewer can lift a pin to the ground it stands on.

On this camera 10 m of height moves a point about 34 pixels up the canvas, so a pin placed at sea level on a hill lands
on the wrong street. A 25 m grid in decimetres is a few kilobytes for a district and close enough for a pin.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from qipu_map.model import Raster

GROUND_CELL_M = 25.0


def ground_grid(terrain: Raster, cell_m: float = GROUND_CELL_M) -> dict[str, Any]:
    """The terrain averaged into `cell_m` blocks, north-up, in whole decimetres (cells with no data read 0)."""
    k = max(1, round(cell_m / terrain.cell))
    h, w = terrain.data.shape
    rows, cols = math.ceil(h / k), math.ceil(w / k)
    padded = np.full((rows * k, cols * k), np.nan, dtype=np.float64)
    padded[:h, :w] = terrain.data
    blocks = padded.reshape(rows, k, cols, k)
    counts = np.isfinite(blocks).sum(axis=(1, 3))
    sums = np.nansum(blocks, axis=(1, 3))
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    decimetres = np.rint(means * 10).astype(np.int64)
    return {
        "x0": float(terrain.x0),
        "y0": float(terrain.y0),
        "cell": float(terrain.cell * k),
        "cols": cols,
        "rows": rows,
        "decimetres": [int(v) for v in decimetres.ravel()],
    }
