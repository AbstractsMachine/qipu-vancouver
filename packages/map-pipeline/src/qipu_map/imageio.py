"""Reading and writing the pipeline's images (render passes, painted canvases, era layers, tiles) as numpy arrays.

PNGs are written without metadata, so the same pixels give the same bytes, and through a temporary name. Three
compression settings cover every use: `fast` for the paint stage's tile cache, written thousands of times a run;
`small` for files that are published and downloaded; `default` for the rest.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO, Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from qipu_map.files import write_atomic

Pixels = NDArray[np.uint8]
Mode = Literal["L", "RGB", "RGBA"]
Compression = Literal["fast", "default", "small"]

_PNG_OPTIONS: dict[Compression, dict[str, Any]] = {
    "fast": {"compress_level": 1},
    "default": {"compress_level": 6},
    "small": {"optimize": True},
}
_GREY = frozenset({"1", "L", "I", "I;16"})


def read_image(source: Path | BinaryIO, mode: Mode | None = None) -> Pixels:
    """An image file (or its bytes in a buffer) as uint8 (h, w) for L, else (h, w, 3) or (h, w, 4). With no mode, the
    file decides: greyscale stays greyscale, an image with transparency comes back RGBA, anything else RGB."""
    with Image.open(source) as im:
        return np.asarray(im.convert(mode or _mode_of(im)), dtype=np.uint8)


def image_size(path: Path) -> tuple[int, int]:
    """(width, height), read from the file's header."""
    with Image.open(path) as im:
        return im.size


def _mode_of(im: Image.Image) -> Mode:
    if im.mode in _GREY:
        return "L"
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        return "RGBA"
    return "RGB"


def array_mode(a: Pixels) -> Mode:
    if a.ndim == 2:
        return "L"
    if a.ndim == 3 and a.shape[2] in (3, 4):
        return "RGB" if a.shape[2] == 3 else "RGBA"
    raise ValueError(f"an image is (h, w), (h, w, 3) or (h, w, 4), got {a.shape}")


def png_bytes(a: Pixels, compression: Compression = "default") -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(a), array_mode(a)).save(buf, format="PNG", **_PNG_OPTIONS[compression])
    return buf.getvalue()


def write_png(path: Path, a: Pixels, compression: Compression = "default") -> None:
    write_atomic(path, png_bytes(a, compression))
