"""Where two painted canvases differ, as the eye would see it.

Two paintings of the same street are never equal to the pixel: the painter's grain moves. Both images are blurred a
little first, and a pixel counts as changed when one channel moves by more than about a tenth of its range, or when one
side is painted and the other is not.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from qipu_map.imageio import Pixels
from qipu_map.imageops import blur_u8, halve_rgba, to_rgba

BLUR_PX = 2.0
THRESHOLD = 26
OPAQUE = 128


def blurred(rgb: Pixels, radius: float = BLUR_PX) -> NDArray[np.int16]:
    return blur_u8(rgb, radius).astype(np.int16)


def changed_mask(a: NDArray[np.uint8], b: NDArray[np.uint8]) -> NDArray[np.bool_]:
    """True where canvas `a` and canvas `b` (RGB or RGBA, same size) look different."""
    if a.shape[:2] != b.shape[:2]:
        raise ValueError(f"canvases differ in size: {a.shape[:2]} and {b.shape[:2]}")
    a4, b4 = to_rgba(a), to_rgba(b)
    colour = np.abs(blurred(a4[..., :3]) - blurred(b4[..., :3])).max(axis=-1) > THRESHOLD
    painted = (a4[..., 3] >= OPAQUE) != (b4[..., 3] >= OPAQUE)
    out: NDArray[np.bool_] = colour | painted
    return out


def shrink(image: NDArray[Any], size: tuple[int, int], *, labels: bool = False) -> NDArray[Any]:
    """`image` brought down to `size` (width, height), one of its pyramid levels (each side halved and rounded up).

    A past year can be painted a level or two coarser than today; today's canvas is then compared at the past year's
    size. Colours are halved as the tile pyramid halves them (premultiplied by alpha, so transparent pixels do not
    darken the edge of what is painted); labels (class and building ids) are sampled, never mixed.
    """
    h, w = image.shape[:2]
    if (w, h) == size:
        return image
    k = 2
    while k <= max(w, h) and (-(-w // k), -(-h // k)) != size:
        k *= 2
    if k > max(w, h):
        raise ValueError(f"a {w} x {h} image cannot be brought to a pyramid level of {size[0]} x {size[1]}")
    if labels:
        return image[::k, ::k]
    out = to_rgba(image)
    while out.shape[:2] != (size[1], size[0]):
        out = halve_rgba(out)
    return out


def composite(layer: Pixels, base: Pixels) -> Pixels:
    """What the viewer shows: `layer` (RGBA) over `base`."""
    base4 = to_rgba(base).astype(np.float32)
    alpha = layer[..., 3:4].astype(np.float32) / 255.0
    rgb = layer[..., :3].astype(np.float32) * alpha + base4[..., :3] * (1.0 - alpha)
    a = np.maximum(base4[..., 3], layer[..., 3].astype(np.float32))
    return np.dstack([np.round(rgb), a]).astype(np.uint8)
