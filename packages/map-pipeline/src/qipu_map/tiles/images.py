"""Encoding a map tile, and the check that refuses a black one."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from qipu_map.imageio import Pixels, read_image
from qipu_map.imageops import to_rgba

# The painted tiles on qipu.org are lossy WebP at quality 90, Pillow's default effort (method 4). The plain render
# tiles before the paint pass used 80; the painted ones went up to 88 and then 90.
WEBP_QUALITY = 90
WEBP_METHOD = 4


def encode_webp(tile: Pixels) -> bytes:
    """An RGBA tile as lossy WebP. A fully opaque tile is written without an alpha channel: same picture, smaller
    file."""
    rgba = to_rgba(tile)
    opaque = bool((rgba[..., 3] == 255).all())
    im = Image.fromarray(rgba[..., :3] if opaque else rgba, "RGB" if opaque else "RGBA")
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    return buf.getvalue()


def decode(data: bytes) -> Pixels:
    """A tile file back to an RGBA array."""
    return read_image(io.BytesIO(data), "RGBA")


def is_near_black(tile: Pixels, limit: int = 12) -> bool:
    """True when a tile's visible pixels are all close to black.

    Such a tile is refused: it reads as a hole in the map, and the fix belongs upstream, in the frame or the paint pass
    that made it.
    """
    rgba = to_rgba(tile)
    visible = rgba[..., 3] > 0
    return bool(visible.any()) and int(np.max(rgba[..., :3][visible])) < limit
