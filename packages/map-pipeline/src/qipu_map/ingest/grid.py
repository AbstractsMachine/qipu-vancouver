"""Grids in local metres: where their cells are, how a source raster is sampled onto them, how they are stored.

Pure numpy, so the resampling can be tested on small arrays and run without the `lidar` extra.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from qipu_map.geo.boxes import WorldBox
from qipu_map.model import Raster

Affine = tuple[float, float, float, float, float, float]  # GDAL order: x = c + col*a + row*b, y = f + col*d + row*e
NODATA_DM = np.iinfo(np.int16).min
_F = NDArray[np.float64]


@dataclass(frozen=True)
class LocalGrid:
    """A north-up grid: (x0, y0) is the north-west corner, `w` columns east and `h` rows south of `cell` metres."""

    x0: float
    y0: float
    cell: float
    w: int
    h: int

    @classmethod
    def covering(cls, box: WorldBox, margin_m: float, cell: float = 1.0) -> LocalGrid:
        """The smallest grid on whole cells that holds the box (x0, y0, x1, y1) grown by the margin."""
        x0 = math.floor((box[0] - margin_m) / cell) * cell
        y1 = math.ceil((box[3] + margin_m) / cell) * cell
        w = math.ceil((box[2] + margin_m - x0) / cell)
        h = math.ceil((y1 - (box[1] - margin_m)) / cell)
        return cls(x0, y1, cell, w, h)

    def centres(self) -> tuple[_F, _F]:
        """(X, Y) of every cell centre, each shaped (h, w)."""
        xs = self.x0 + (np.arange(self.w) + 0.5) * self.cell
        ys = self.y0 - (np.arange(self.h) + 0.5) * self.cell
        xx, yy = np.meshgrid(xs, ys)
        return xx, yy


def sample_nearest(
    data: NDArray[np.float32], transform: Affine, nodata: float | None, ex: _F, ny: _F
) -> NDArray[np.float32]:
    """The value of the source cell each (ex, ny) point falls in, NaN outside the source or on its nodata.

    Nearest cell, so a building edge stays a step, it is not smeared over two cells.
    The transform must be north-up (no rotation), which every LiDAR tile here is.
    """
    a, b, c, d, e, f = transform
    if b != 0.0 or d != 0.0:
        raise ValueError("rotated rasters are not supported")
    col = np.floor((ex - c) / a).astype(np.int64)
    row = np.floor((ny - f) / e).astype(np.int64)
    h, w = data.shape
    inside = (col >= 0) & (col < w) & (row >= 0) & (row < h)
    out = np.full(ex.shape, np.nan, np.float32)
    vals = data[row[inside], col[inside]].astype(np.float32)
    if nodata is not None:
        vals[vals == np.float32(nodata)] = np.nan
    out[inside] = vals
    return out


def fill_missing(acc: NDArray[np.float32], new: NDArray[np.float32]) -> NDArray[np.float32]:
    """`acc` with its NaN cells taken from `new`: where two tiles overlap, the first one read wins."""
    return np.where(np.isnan(acc), new, acc).astype(np.float32)


def to_decimetres(values: NDArray[np.float32]) -> NDArray[np.int16]:
    """Heights in metres to int16 decimetres (±3,276 m), NaN to the int16 minimum. Halves the stored size."""
    dm = np.round(np.nan_to_num(values, nan=0.0) * 10.0)
    out = np.clip(dm, NODATA_DM + 1, np.iinfo(np.int16).max).astype(np.int16)
    out[np.isnan(values)] = NODATA_DM
    return out


def from_decimetres(dm: NDArray[np.int16]) -> NDArray[np.float32]:
    out = dm.astype(np.float32) / 10.0
    out[dm == NODATA_DM] = np.nan
    return out


def grid_bytes(grid: LocalGrid, values: NDArray[np.float32]) -> bytes:
    """A grid as a compressed .npz of int16 decimetres, the raw folder's LiDAR format."""
    buf = io.BytesIO()
    np.savez_compressed(buf, dm=to_decimetres(values), x0=grid.x0, y0=grid.y0, cell=grid.cell)
    return buf.getvalue()


def load_grid(path: Path) -> Raster:
    """Read a grid written by `grid_bytes` as a `Raster` of heights in metres, NaN where the source had no data."""
    with np.load(path) as z:
        return Raster(float(z["x0"]), float(z["y0"]), float(z["cell"]), from_decimetres(z["dm"]))
