"""Quilting: join overlapping painted tiles into one canvas.

Each tile is painted from its own noise, so two tiles never agree exactly where they overlap. Averaging them gives
see-through buildings and ghost towers, so each pixel is taken from one tile instead and hides the change along
a seam. In each overlap the seam is the cheapest top-to-bottom path through a band of +-200 px around the overlap's
middle (a dynamic program over rows), where the cost is how much the two tiles differ there, plus a large cost on the
render's facades, so seams go round buildings instead of cutting one in two. Across the seam the tiles are feathered
over 12 px (two weights that always sum to 1).

Tiles are joined into row strips left to right, then the strips top to bottom, the same seam rule turned on its side.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from qipu_map.imageops import gaussian

Floats = NDArray[np.float32]
WALL_COST = 60.0
FEATHER = 6
BAND_MARGIN = 56


def band_for(tile: int, stride: int) -> int:
    """Half-width of the band the seam may move in: the overlap's half-width less a margin (200 px for 1024 / 512)."""
    half = (tile - stride) // 2
    return max(0, min(half, max(FEATHER + 1, half - BAND_MARGIN)))


def seam(cost: Floats) -> NDArray[np.int64]:
    """The column of the cheapest top-to-bottom path through `cost` (h, w), moving at most one column per row."""
    h, w = cost.shape
    acc = cost.astype(np.float64)
    back = np.zeros((h, w), np.int8)
    inf = np.array([np.inf])
    for y in range(1, h):
        prev = acc[y - 1]
        choices = np.stack([np.concatenate((inf, prev[:-1])), prev, np.concatenate((prev[1:], inf))])
        k = choices.argmin(0)
        acc[y] += choices[k, np.arange(w)]
        back[y] = k - 1
    path = np.zeros(h, np.int64)
    path[-1] = int(acc[-1].argmin())
    for y in range(h - 1, 0, -1):
        path[y - 1] = min(w - 1, max(0, path[y] + back[y, path[y]]))
    return path


def seam_weights(path: NDArray[np.int64], width: int, feather: int = FEATHER) -> Floats:
    """(h, width) weight of the right-hand tile: 0 left of the seam, 1 right of it, a linear ramp of 2 * feather px."""
    xx = np.arange(width)[None, :]
    out: Floats = np.clip((xx - path[:, None] + feather) / (2 * feather), 0.0, 1.0).astype(np.float32)
    return out


def join(a: Floats, b: Floats, walls: NDArray[np.bool_]) -> Floats:
    """Blend two images of the same (h, w) band, left `a` and right `b`, along their cheapest vertical seam."""
    diff = np.abs(a - b).mean(-1)
    cost = gaussian(diff, 2.0) + WALL_COST * gaussian(walls.astype(np.float32), 1.0)
    w = seam_weights(seam(cost), a.shape[1])[..., None]
    out: Floats = (a * (1.0 - w) + b * w).astype(np.float32)
    return out


def quilt(
    xs: list[int],
    ys: list[int],
    tile: int,
    load: Callable[[int, int], Floats],
    walls: NDArray[np.bool_],
) -> Floats:
    """Quilt the grid of tiles at world positions xs x ys (equal stride) into one image whose top-left is (xs[0],
    ys[0]).

    `load(x, y)` gives a tile as float32 (tile, tile, 3); `walls` is the facade mask over the same image.
    """
    stride = xs[1] - xs[0] if len(xs) > 1 else tile
    vstride = ys[1] - ys[0] if len(ys) > 1 else tile
    width, height = xs[-1] + tile - xs[0], ys[-1] + tile - ys[0]
    out = np.zeros((height, width, 3), np.float32)
    for r, y in enumerate(ys):
        top = y - ys[0]
        strip = _strip(xs, y, tile, stride=stride, load=load, walls=walls[top : top + tile])
        if r == 0:
            out[:tile] = strip
            continue
        band = band_for(tile, vstride)
        mid = top + (tile - vstride) // 2
        b0, b1 = mid - band, mid + band
        if band > 0:
            a_band = out[b0:b1].transpose(1, 0, 2)
            s_band = strip[b0 - top : b1 - top].transpose(1, 0, 2)
            out[b0:b1] = join(a_band, s_band, walls[b0:b1].T).transpose(1, 0, 2)
        out[b1 : top + tile] = strip[b1 - top :]
    return out


def _strip(
    xs: list[int], y: int, tile: int, *, stride: int, load: Callable[[int, int], Floats], walls: NDArray[np.bool_]
) -> Floats:
    width = xs[-1] + tile - xs[0]
    strip = np.zeros((tile, width, 3), np.float32)
    band = band_for(tile, stride)
    for i, x in enumerate(xs):
        t = load(x, y)
        left = x - xs[0]
        if i == 0:
            strip[:, :tile] = t
            continue
        mid = left + (tile - stride) // 2
        a0, a1 = mid - band, mid + band
        if band > 0:
            strip[:, a0:a1] = join(strip[:, a0:a1], t[:, a0 - left : a1 - left], walls[:, a0:a1])
        strip[:, a1 : left + tile] = t[:, a1 - left :]
    return strip
