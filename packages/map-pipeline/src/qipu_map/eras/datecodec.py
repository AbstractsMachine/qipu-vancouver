"""The date-map encoding of docs/tiles-format.md: a decimal year in 16 bits, stored as R*256+G of an 8-bit RGB PNG.

n = round((year - 1800) * 100), so a date is kept to a hundredth of a year (about 3.7 days) from 1800 to 2455.
n = 65535 means the pixel does not change in the segment. B is always 0.
"""

from __future__ import annotations

import io

import numpy as np
from numpy.typing import NDArray

from qipu_map.imageio import png_bytes, read_image

EPOCH = 1800.0
NEVER = 65535
_LAST = NEVER - 1

DateMap = NDArray[np.uint16]


def encode_dates(dates: NDArray[np.floating]) -> DateMap:
    """Decimal years to the 16-bit code; NaN means never. Dates are clamped to what the code can hold."""
    d = np.asarray(dates, dtype=np.float64)
    never = np.isnan(d)
    n = np.clip(np.round((np.where(never, EPOCH, d) - EPOCH) * 100.0), 0, _LAST)
    out: DateMap = np.where(never, NEVER, n).astype(np.uint16)
    return out


def decode_dates(codes: DateMap) -> NDArray[np.float64]:
    """The 16-bit code to decimal years, NaN for never."""
    c = np.asarray(codes)
    return np.where(c == NEVER, np.nan, EPOCH + c.astype(np.float64) / 100.0)


def to_rgb(codes: DateMap) -> NDArray[np.uint8]:
    """The codes as an (h, w, 3) 8-bit image: R the high byte, G the low byte, B zero."""
    c = np.asarray(codes, dtype=np.uint16)
    return np.dstack([(c >> 8).astype(np.uint8), (c & 0xFF).astype(np.uint8), np.zeros(c.shape, np.uint8)])


def from_rgb(rgb: NDArray[np.uint8]) -> DateMap:
    """The 16-bit codes of a date-map image: R*256+G of each pixel. B is ignored."""
    out: DateMap = (rgb[..., 0].astype(np.uint16) * 256 + rgb[..., 1]).astype(np.uint16)
    return out


def reduce_min(codes: DateMap) -> DateMap:
    """Half the size, each pixel the earliest of the 2x2 under it, so nothing appears late when zoomed out.

    An odd edge is padded with "never", which loses to any date. "Never" is the largest code, so a plain minimum works.
    """
    c = np.asarray(codes, dtype=np.uint16)
    h, w = c.shape
    padded = np.full((h + h % 2, w + w % 2), NEVER, np.uint16)
    padded[:h, :w] = c
    out: DateMap = padded.reshape(padded.shape[0] // 2, 2, padded.shape[1] // 2, 2).min(axis=(1, 3))
    return out


def encode_png(codes: DateMap, tile_size: int | None = None) -> bytes:
    """One date-map tile as PNG bytes. A short edge tile is padded with "never" to `tile_size`, as the format asks."""
    c = np.asarray(codes, dtype=np.uint16)
    if tile_size is not None and c.shape != (tile_size, tile_size):
        full = np.full((tile_size, tile_size), NEVER, np.uint16)
        full[: c.shape[0], : c.shape[1]] = c
        c = full
    return png_bytes(to_rgb(c), "small")


def decode_png(data: bytes) -> DateMap:
    return from_rgb(read_image(io.BytesIO(data), "RGB"))


def is_never(codes: DateMap) -> bool:
    """True for a tile where nothing changes: the pyramid writer skips it."""
    return bool((np.asarray(codes) == NEVER).all())
