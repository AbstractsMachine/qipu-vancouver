"""The `have` bitmaps of the manifest: which tiles of a zoom level exist.

Bit `i = (y - y0) * cols + (x - x0)` is set when tile (x, y) exists, eight bits to a byte, most significant bit first,
base64-encoded. These two functions are the only place that knows the bit order.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from typing import TypedDict


class Have(TypedDict):
    x0: int
    y0: int
    cols: int
    rows: int
    bits: str


def pack_have(tiles: Iterable[tuple[int, int]]) -> Have:
    """The smallest box around `tiles` and the bitmap of which of its cells are tiles."""
    keys = sorted(set(tiles))
    if not keys:
        raise ValueError("a have bitmap needs at least one tile")
    xs, ys = [x for x, _ in keys], [y for _, y in keys]
    x0, y0 = min(xs), min(ys)
    cols, rows = max(xs) - x0 + 1, max(ys) - y0 + 1
    bits = bytearray((cols * rows + 7) // 8)
    for x, y in keys:
        i = (y - y0) * cols + (x - x0)
        bits[i >> 3] |= 0x80 >> (i & 7)
    return Have(x0=x0, y0=y0, cols=cols, rows=rows, bits=base64.b64encode(bytes(bits)).decode("ascii"))


def unpack_have(have: Have) -> set[tuple[int, int]]:
    """The tiles a `have` bitmap says exist."""
    bits = base64.b64decode(have["bits"])
    cols, rows = have["cols"], have["rows"]
    if len(bits) != (cols * rows + 7) // 8:
        raise ValueError(f"have bitmap is {len(bits)} bytes, expected {(cols * rows + 7) // 8} for {cols} x {rows}")
    return {
        (have["x0"] + i % cols, have["y0"] + i // cols) for i in range(cols * rows) if bits[i >> 3] & (0x80 >> (i & 7))
    }
