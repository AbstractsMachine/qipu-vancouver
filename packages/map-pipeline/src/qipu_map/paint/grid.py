"""The world tile grid the painter works on.

Tiles are `tile` px squares placed every `stride` px (1024 and 512 for Vancouver, so every pixel is painted by four
tiles and the quilt keeps one). The grid is fixed to the world, not to the area being painted: positions are in world
pixels, the canvas pixel plus the canvas's offset in the camera's screen plane (`origin`). So a tile at a place has
the same position, the same seed and the same noise in every run, every area that contains it and every year, which
is what lets a re-run or a past year reuse tiles whose input did not change.

A tile that hangs over the canvas edge reads the render mirrored at the edge. Black padding is never used: FLUX paints
a black margin as sea.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray

from qipu_map.hashing import stable_seed

T = TypeVar("T", bound=np.generic)


@dataclass(frozen=True)
class Tile:
    """A tile by its top-left corner in world pixels."""

    x: int
    y: int

    @property
    def key(self) -> str:
        return f"{self.x}_{self.y}"


@dataclass(frozen=True)
class Grid:
    """The world tile grid over one canvas: `tile` px tiles every `stride` px, fixed to the world through `origin`."""

    tile: int
    stride: int
    origin: tuple[int, int]  # the canvas's top-left pixel in world pixels
    width: int  # canvas size
    height: int

    def __post_init__(self) -> None:
        if not 0 < self.stride <= self.tile:
            raise ValueError("stride must be in (0, tile]")

    def tiles(self) -> list[Tile]:
        """Every tile that touches the canvas, row by row."""
        ox, oy = self.origin
        xs = range(_first(ox, self.tile, self.stride), ox + self.width, self.stride)
        ys = range(_first(oy, self.tile, self.stride), oy + self.height, self.stride)
        return [Tile(x, y) for y in ys for x in xs]


def _first(o: int, tile: int, stride: int) -> int:
    """The leftmost grid position whose tile still reaches past canvas pixel 0 (world `o`)."""
    return ((o - tile) // stride + 1) * stride


def seed_for(x: int, y: int, salt: int | str) -> int:
    """A 32-bit seed from a world position (SHA-1 of the salt and the position)."""
    return stable_seed(f"{salt}:{x},{y}")


def crop_reflect(image: NDArray[T], x0: int, y0: int, w: int, h: int) -> NDArray[T]:
    """The w x h window at canvas (x0, y0), mirrored at the canvas edges where it hangs over them.

    Mirroring repeats as often as needed, so a window larger than the canvas still gets image content everywhere.
    """
    ih, iw = image.shape[:2]
    ys = _reflect_index(np.arange(y0, y0 + h), ih)
    xs = _reflect_index(np.arange(x0, x0 + w), iw)
    out: NDArray[T] = image[ys[:, None], xs[None, :]]
    return out


def _reflect_index(i: NDArray[np.int_], n: int) -> NDArray[np.int_]:
    """Indices mirrored into [0, n): ... 2 1 0 | 0 1 2 ... n-1 | n-1 n-2 ... (edge pixel repeated, as numpy's
    'symmetric')."""
    if n == 1:
        return np.zeros_like(i)
    period = 2 * n
    m = np.mod(i, period)
    out: NDArray[np.int_] = np.where(m < n, m, period - 1 - m)
    return out
