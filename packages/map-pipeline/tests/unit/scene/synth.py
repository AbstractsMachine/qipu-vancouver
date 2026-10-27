"""Small synthetic surfaces for the scene tests: a flat ground with roofs of known shape on it."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from qipu_map.model import Raster

GROUND_M = 20.0
SIZE = 40  # cells (1 m) on a side; the grid covers x 0..40, y 0..40


def grid(fill: float = GROUND_M, size: int = SIZE) -> Raster:
    return Raster(0.0, float(size), 1.0, np.full((size, size), fill, dtype=np.float32))


def centres(r: Raster) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    h, w = r.data.shape
    return np.meshgrid(r.x0 + np.arange(w) + 0.5, r.y0 - np.arange(h) - 0.5)


def with_roof(
    box: tuple[float, float, float, float],
    height: Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]],
) -> Raster:
    """A DSM: the ground, and inside `box` (x0, y0, x1, y1) the ground plus `height(x, y)`."""
    r = grid()
    x, y = centres(r)
    inside = (x > box[0]) & (x < box[2]) & (y > box[1]) & (y < box[3])
    data = r.data.astype(np.float64)
    data[inside] += height(x, y)[inside]
    return Raster(r.x0, r.y0, r.cell, data.astype(np.float32))


HOUSE = (10.0, 10.0, 20.0, 26.0)  # 10 m wide (x), 16 m deep (y)


def gable(eave: float = 6.0, slope: float = 0.9, along_y: bool = True) -> Raster:
    """A gable on HOUSE: its ridge along y (the long side) by default, rising `slope` m per m from the eaves."""
    cx, cy = 15.0, 18.0
    if along_y:
        return with_roof(HOUSE, lambda x, _y: eave + slope * (5.0 - np.abs(x - cx)))
    return with_roof(HOUSE, lambda _x, y: eave + slope * (8.0 - np.abs(y - cy)))


def hip(eave: float = 6.0, slope: float = 0.9) -> Raster:
    return with_roof(
        HOUSE, lambda x, y: eave + slope * np.minimum(np.minimum(x - 10.0, 20.0 - x), np.minimum(y - 10.0, 26.0 - y))
    )


def flat(height: float = 10.0) -> Raster:
    return with_roof(HOUSE, lambda x, _y: np.full_like(x, height))
