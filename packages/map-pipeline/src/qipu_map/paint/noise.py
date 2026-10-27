"""World-anchored start noise.

A diffusion model starts from noise. If each tile drew its own noise, two overlapping tiles would paint the same place
differently and the quilt would have to hide the difference. Here the noise is one field over the whole world: its cells
(one latent cell = 16 px at the level being painted) come in chunks of 16 x 16 cells, each chunk drawn from a generator
seeded by (noise key, level, chunk position). Two tiles that overlap get the same noise where they overlap, and a tile
gets the same noise in every run. A re-roll changes the noise key, which repaints the tile: a new seed alone would not,
since the noise is passed in.

The chunks are drawn with numpy's generator, so the field can be built and tested without torch.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from qipu_map.hashing import stable_seed

CELL_PX = 16  # pixels of a 1024 px tile per latent cell
CHUNK = 16  # latent cells per noise chunk side


def chunk_seed(key: str, level: int, cx: int, cy: int) -> int:
    return stable_seed(f"{key}{level}:{cx},{cy}", bits=60)


def noise_field(key: str, level: int, x0: int, y0: int, *, n: int, channels: int) -> NDArray[np.float32]:
    """(channels, n, n) standard normal noise for the n x n latent cells whose top-left cell is (x0, y0) in world
    cells."""
    z = np.empty((channels, n, n), np.float32)
    for cy in range(y0 // CHUNK, (y0 + n - 1) // CHUNK + 1):
        for cx in range(x0 // CHUNK, (x0 + n - 1) // CHUNK + 1):
            rng = np.random.default_rng(chunk_seed(key, level, cx, cy))
            chunk = rng.standard_normal((channels, CHUNK, CHUNK), dtype=np.float32)
            ax, ay = cx * CHUNK, cy * CHUNK
            sx0, sy0 = max(ax, x0), max(ay, y0)
            sx1, sy1 = min(ax + CHUNK, x0 + n), min(ay + CHUNK, y0 + n)
            z[:, sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = chunk[:, sy0 - ay : sy1 - ay, sx0 - ax : sx1 - ax]
    return z
