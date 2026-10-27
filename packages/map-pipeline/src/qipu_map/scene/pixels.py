"""Reading a raster under a footprint: the cells whose centres fall inside a polygon, and a window around it."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.model import Raster


@dataclass(frozen=True)
class Window:
    """A block of a raster's cells: rows i0..i1 and columns j0..j1 (end exclusive), and the block's values."""

    i0: int
    j0: int
    values: NDArray[np.float32]
    cell: float
    x0: float
    y0: float

    def centres(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """The world x and y of every cell centre in the window, as two arrays shaped like `values`."""
        h, w = self.values.shape
        xs = self.x0 + (self.j0 + np.arange(w) + 0.5) * self.cell
        ys = self.y0 - (self.i0 + np.arange(h) + 0.5) * self.cell
        gx, gy = np.meshgrid(xs, ys)
        return gx, gy


def window(r: Raster, bounds: tuple[float, float, float, float], margin: int = 0) -> Window:
    """The cells covering `bounds` (x0, y0, x1, y1) plus `margin` cells all round, clamped to the raster."""
    h, w = r.data.shape
    j0 = max(0, math.floor((bounds[0] - r.x0) / r.cell) - margin)
    j1 = min(w, math.ceil((bounds[2] - r.x0) / r.cell) + margin)
    i0 = max(0, math.floor((r.y0 - bounds[3]) / r.cell) - margin)
    i1 = min(h, math.ceil((r.y0 - bounds[1]) / r.cell) + margin)
    values = r.data[i0 : max(i0, i1), j0 : max(j0, j1)]
    return Window(i0, j0, values, r.cell, r.x0, r.y0)


def inside(win: Window, poly: shapely.Polygon) -> NDArray[np.bool_]:
    """True for the window's cells whose centre lies inside the polygon."""
    gx, gy = win.centres()
    return np.asarray(shapely.contains_xy(poly, gx, gy), dtype=bool)


def inset(poly: shapely.Polygon, metres: float, min_area: float = 4.0) -> shapely.Polygon:
    """The polygon drawn `metres` in, so walls and eaves (which read half ground) stay out; whole if that leaves too
    little."""
    shrunk = poly.buffer(-metres)
    if shrunk.is_empty or shrunk.area < min_area:
        return poly
    if isinstance(shrunk, shapely.MultiPolygon):
        return max(shrunk.geoms, key=lambda g: g.area)
    return shrunk if isinstance(shrunk, shapely.Polygon) else poly
