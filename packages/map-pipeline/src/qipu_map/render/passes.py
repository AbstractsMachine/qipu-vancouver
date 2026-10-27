"""The three images a frame is written as, and their pixel encodings.

`<name>.beauty.png`  RGB, the picture.
`<name>.class.png`   8-bit greyscale, each pixel a `classes.SurfaceClass` id.
`<name>.id.png`      RGB, each pixel a building: id = R << 16 | G << 8 | B is 1 + the building's index in
                     `scene.buildings`, 0 where no building shows. 24 bits hold 16.7 million buildings, and a
                     plain RGB PNG opens anywhere.

A renderer that cannot write ids directly draws the class pass in the flat colours of `classes.CLASS_COLOURS` and
`classes_from_rgb` maps them back. It takes the nearest colour, so a stray filtered edge pixel still lands on a class.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from qipu_map.classes import CLASS_COLOURS, SurfaceClass

Kind = Literal["beauty", "class", "id"]
KINDS: tuple[Kind, ...] = ("beauty", "class", "id")


def pass_path(out_dir: Path, frame: str, kind: Kind) -> Path:
    """The file of one frame's pass: `<out_dir>/<frame>.<kind>.png`."""
    return out_dir / f"{frame}.{kind}.png"


def encode_ids(ids: NDArray[np.integer]) -> NDArray[np.uint8]:
    """An (h, w) array of building ids (0..2^24-1) to an (h, w, 3) RGB array."""
    a = ids.astype(np.uint32)
    if a.size and int(np.max(a)) >= 1 << 24:
        raise ValueError("building ids must fit in 24 bits")
    return np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255], axis=-1).astype(np.uint8)


def decode_ids(rgb: NDArray[np.generic]) -> NDArray[np.uint32]:
    """An (h, w, 3) id-pass image to an (h, w) array of ids: 1 + the building's index in `scene.buildings`, 0 where
    none."""
    a = rgb.astype(np.uint32)
    out: NDArray[np.uint32] = ((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]).astype(np.uint32)
    return out


def id_colour(index: int) -> tuple[int, int, int]:
    """The id-pass colour of the building at `index` in `scene.buildings`."""
    v = index + 1
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def classes_from_rgb(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """A class pass drawn in `CLASS_COLOURS` to class ids, by nearest colour."""
    ids = np.array([int(c) for c in CLASS_COLOURS], dtype=np.uint8)
    palette = np.array([CLASS_COLOURS[SurfaceClass(int(i))] for i in ids], dtype=np.int32)
    flat = rgb.reshape(-1, 3).astype(np.int32)
    colours, inverse = np.unique(flat, axis=0, return_inverse=True)
    dist = ((colours[:, None, :] - palette[None, :, :]) ** 2).sum(-1)
    out: NDArray[np.uint8] = ids[dist.argmin(1)][inverse.reshape(-1)].reshape(rgb.shape[:2])
    return out


def class_colours(classes: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Class ids to their flat colours, for looking at a class pass."""
    lut = np.zeros((256, 3), dtype=np.uint8)
    for c, rgb in CLASS_COLOURS.items():
        lut[int(c)] = rgb
    out: NDArray[np.uint8] = lut[classes]
    return out


def write_png(path: Path, a: NDArray[np.uint8]) -> None:
    """Write without metadata or timestamps, so the same pixels give the same bytes."""
    mode = "L" if a.ndim == 2 else "RGB"
    Image.fromarray(a, mode=mode).save(path, format="PNG", optimize=False, compress_level=6)


def read_png(path: Path) -> NDArray[np.uint8]:
    """Read a pass PNG as uint8, (h, w) for greyscale and (h, w, 3) for colour."""
    with Image.open(path) as im:
        a: NDArray[np.uint8] = np.asarray(
            im.convert("L" if im.mode in ("L", "P", "I", "I;16") else "RGB"), dtype=np.uint8
        )
    return a
