"""Cut an image into a tile pyramid, as docs/tiles-format.md lays it out.

The image is the deepest zoom, `zmax`. Each level above is the one below halved, until the picture fits in one tile
(zoom 0). Level z is `ceil(width / 2^(zmax - z))` pixels wide; halving with a ceiling at every step gives the same
sizes, so a reducer pads an odd edge with transparent pixels. Tiles are cut from the top-left, edge tiles are padded to
full size, and a tile with nothing in it is not written at all: the `have` bitmaps tell the viewer not to ask for it.

The pyramid is built from the whole image at each level, so a downsampled tile sees its neighbours' pixels and there is
no seam where four children meet, as there is when each tile is halved from its four children alone.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray

from qipu_map.files import read_json, write_atomic, write_json
from qipu_map.tiles.have import Have, pack_have, unpack_have

PYRAMID_FILE = "pyramid.json"

TileKey = tuple[int, int]
T = TypeVar("T", bound=np.generic)  # the pixel type: uint8 for RGBA layers, uint16 for date maps


@dataclass(frozen=True)
class Pyramid:
    """What a pyramid holds: its deepest zoom and, per zoom, the tiles that were written."""

    zmax: int
    tile_size: int
    suffix: str
    tiles: Mapping[int, frozenset[TileKey]]

    def have(self) -> dict[str, Have]:
        """The manifest's `have`: one bitmap per zoom that has tiles."""
        return {str(z): pack_have(self.tiles[z]) for z in sorted(self.tiles) if self.tiles[z]}

    def paths(self) -> Iterator[str]:
        """Every tile's path relative to the pyramid folder (`z/x/y.suffix`), in a fixed order."""
        for z in sorted(self.tiles):
            for x, y in sorted(self.tiles[z]):
                yield f"{z}/{x}/{y}{self.suffix}"

    def save(self, out_dir: Path) -> None:
        doc = {"zmax": self.zmax, "tile_size": self.tile_size, "suffix": self.suffix, "have": self.have()}
        write_json(out_dir / PYRAMID_FILE, doc)

    @classmethod
    def load(cls, out_dir: Path) -> Pyramid:
        """Read back the index `write_pyramid` left in a pyramid folder."""
        doc = read_json(out_dir / PYRAMID_FILE)
        tiles = {int(z): frozenset(unpack_have(h)) for z, h in doc["have"].items()}
        return cls(zmax=doc["zmax"], tile_size=doc["tile_size"], suffix=doc["suffix"], tiles=tiles)


def zmax_for(width: int, height: int, tile_size: int) -> int:
    """The deepest zoom of a `width` x `height` canvas: how many halvings it takes to fit in one tile."""
    if width < 1 or height < 1 or tile_size < 1:
        raise ValueError(f"sizes must be positive: {width} x {height}, tile {tile_size}")
    z, side = 0, max(width, height)
    while side > tile_size:
        side = -(-side // 2)
        z += 1
    return z


def level_size(width: int, height: int, zmax: int, z: int) -> tuple[int, int]:
    """The size of zoom `z`'s picture: the canvas halved `zmax - z` times, rounding up."""
    if not 0 <= z <= zmax:
        raise ValueError(f"zoom {z} is outside 0..{zmax}")
    k = 1 << (zmax - z)
    return (-(-width // k), -(-height // k))


def cut_tile(level: NDArray[T], x: int, y: int, tile_size: int, fill: int = 0) -> NDArray[T]:
    """Tile (x, y) of a level, padded with `fill` where it runs past the level's edge."""
    h, w = level.shape[:2]
    part = level[y * tile_size : min((y + 1) * tile_size, h), x * tile_size : min((x + 1) * tile_size, w)]
    if part.shape[:2] == (tile_size, tile_size):
        return part
    out = np.full((tile_size, tile_size, *level.shape[2:]), fill, dtype=level.dtype)
    out[: part.shape[0], : part.shape[1]] = part
    return out


def is_transparent(tile: NDArray[np.generic]) -> bool:
    """True when an RGBA tile has no visible pixel. Tiles without alpha are never empty."""
    return tile.ndim == 3 and tile.shape[2] == 4 and not tile[..., 3].any()


def write_pyramid(
    image: NDArray[T],
    out_dir: Path,
    *,
    tile_size: int,
    encode: Callable[[NDArray[T]], bytes],
    reduce: Callable[[NDArray[T]], NDArray[T]],
    suffix: str,
    is_empty: Callable[[NDArray[T]], bool] = is_transparent,
    fill: int = 0,
) -> Pyramid:
    """Write every zoom of `image` into `out_dir/{z}/{x}/{y}{suffix}` and return what was written.

    `encode` turns a tile into file bytes, `reduce` halves a level (rounding odd sizes up), `is_empty` says which tiles
    to leave out, and `fill` pads edge tiles. Tiles left from an earlier run that this one did not write are removed, so
    the folder always matches the returned pyramid. An index of it is saved as `pyramid.json` for the publish stage.
    """
    height, width = image.shape[:2]
    zmax = zmax_for(width, height, tile_size)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[int, frozenset[TileKey]] = {}
    level = image
    for z in range(zmax, -1, -1):
        if level.shape[:2] != level_size(width, height, zmax, z)[::-1]:
            expected = level_size(width, height, zmax, z)
            raise ValueError(f"reduce gave a {level.shape[1]} x {level.shape[0]} level {z}, expected {expected}")
        written[z] = _write_level(
            level, out_dir / str(z), tile_size=tile_size, encode=encode, suffix=suffix, is_empty=is_empty, fill=fill
        )
        if z > 0:
            level = reduce(level)
    pyramid = Pyramid(zmax=zmax, tile_size=tile_size, suffix=suffix, tiles=written)
    _remove_stale(out_dir, pyramid)
    pyramid.save(out_dir)
    return pyramid


def _write_level(
    level: NDArray[T],
    z_dir: Path,
    *,
    tile_size: int,
    encode: Callable[[NDArray[T]], bytes],
    suffix: str,
    is_empty: Callable[[NDArray[T]], bool],
    fill: int,
) -> frozenset[TileKey]:
    h, w = level.shape[:2]
    keys: set[TileKey] = set()
    for y in range(-(-h // tile_size)):
        for x in range(-(-w // tile_size)):
            tile = cut_tile(level, x, y, tile_size, fill)
            if is_empty(tile):
                continue
            write_atomic(z_dir / str(x) / f"{y}{suffix}", encode(tile))
            keys.add((x, y))
    return frozenset(keys)


def _remove_stale(out_dir: Path, pyramid: Pyramid) -> None:
    keep = {out_dir / p for p in pyramid.paths()}
    for path in sorted(out_dir.glob(f"*/*/*{pyramid.suffix}")):
        if path not in keep and path.parent.parent.name.isdigit():
            path.unlink()
