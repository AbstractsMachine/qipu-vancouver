"""The shared half-resolution layer: the colour anchor every tile is painted against.

Painting each 1024 px tile on its own gives each tile its own idea of the light and colour, and the quilt then shows
patches. So the canvas is painted in two passes. First a layer at half resolution: anchors every 1024 px of the world,
each painting the 2048 px around it shrunk to 1024 px, joined into one layer with feathered cores. Then each tile's full
resolution pass gets two images, its own piece of that layer (blown up to 1024 px) and its render tile, with a prompt
that keeps the render's geometry. Neighbouring tiles thus share their colour from one painting, and the render keeps
slender towers the half-resolution pass would lose.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from qipu_map.paint.backends import RGB, resize
from qipu_map.paint.grid import Tile

Floats = NDArray[np.float32]

# Levels number resolutions the way zoom levels do: one level down halves the resolution. A level is part of every
# painting's noise and cache key.
TILE_LEVEL = 9  # tile level: the full resolution of the canvas
ANCHOR_LEVEL = TILE_LEVEL - 1  # anchor level: half the tile resolution


@dataclass(frozen=True)
class Anchor:
    """An anchor at world (x, y), a multiple of the tile size. It paints world [x - t/2, x + 3t/2) at half
    resolution."""

    x: int
    y: int

    def window(self, tile: int) -> tuple[int, int, int]:
        """(x0, y0, size) of the full-resolution window it reads."""
        return self.x - tile // 2, self.y - tile // 2, 2 * tile

    def half_res_origin(self, tile: int) -> tuple[int, int]:
        """Its output's top-left in half-resolution world pixels."""
        return (self.x - tile // 2) // 2, (self.y - tile // 2) // 2


def core_weight(tile: int) -> Floats:
    """(tile, tile, 1) weight of an anchor's output: 1 in its middle 18/32, ramping to 0 over tile/16 on each side."""
    x = np.arange(tile, dtype=np.float32) + 0.5
    lo, hi, ramp = 7 * tile / 32, 25 * tile / 32, tile / 16
    r = np.clip(np.minimum(x - lo, hi - x) / ramp, 0.0, 1.0)
    out: Floats = np.outer(r, r)[..., None].astype(np.float32)
    return out


def anchors_for(tiles: Iterable[Tile], tile: int) -> list[Anchor]:
    """Every anchor whose weighted core overlaps one of the tiles, sorted row by row."""
    found: set[tuple[int, int]] = set()
    reach_lo, reach_hi = tile // 16, tile + tile // 16  # the core spans world [a - tile/16, a + 17 tile/16)
    for t in tiles:
        for ay in range((t.y - reach_hi) // tile * tile, t.y + tile + reach_lo + 1, tile):
            for ax in range((t.x - reach_hi) // tile * tile, t.x + tile + reach_lo + 1, tile):
                if (
                    ax - reach_lo < t.x + tile
                    and ax + reach_hi > t.x
                    and ay - reach_lo < t.y + tile
                    and ay + reach_hi > t.y
                ):
                    found.add((ay, ax))
    return [Anchor(x, y) for y, x in sorted(found)]


@dataclass(frozen=True)
class AnchorLayer:
    """The joined half-resolution layer; `origin` is its top-left in half-resolution world pixels."""

    image: RGB
    origin: tuple[int, int]

    def context(self, t: Tile, tile: int) -> RGB:
        """The tile's piece of the layer, blown up to full resolution."""
        x0, y0 = t.x // 2 - self.origin[0], t.y // 2 - self.origin[1]
        half = tile // 2
        piece = self.image[y0 : y0 + half, x0 : x0 + half]
        if piece.shape[:2] != (half, half):
            raise ValueError(f"tile {t.key} reads outside the half-resolution layer")
        return resize(np.ascontiguousarray(piece), tile)


def join_layer(painted: dict[Anchor, RGB], tile: int) -> AnchorLayer:
    """Feather the anchors' outputs into one layer (weights normalised where cores overlap)."""
    origins = {a: a.half_res_origin(tile) for a in painted}
    x0 = min(o[0] for o in origins.values())
    y0 = min(o[1] for o in origins.values())
    x1 = max(o[0] for o in origins.values()) + tile
    y1 = max(o[1] for o in origins.values()) + tile
    acc = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
    wsum = np.zeros((y1 - y0, x1 - x0, 1), np.float32)
    weight = core_weight(tile)
    for a in sorted(painted, key=lambda a: (a.y, a.x)):
        ox, oy = origins[a][0] - x0, origins[a][1] - y0
        acc[oy : oy + tile, ox : ox + tile] += painted[a].astype(np.float32) * weight
        wsum[oy : oy + tile, ox : ox + tile] += weight
    image: RGB = np.clip(acc / np.maximum(wsum, 1e-6) + 0.5, 0, 255).astype(np.uint8)
    return AnchorLayer(image, (x0, y0))
