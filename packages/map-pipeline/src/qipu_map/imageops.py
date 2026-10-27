"""Image operations in plain numpy: square dilation and erosion, a running maximum, box and Gaussian blur, connected
components, and RGBA conversion and halving.

The painter's guards, the canopy finder of the scene and the era layers need these on arrays up to a few thousand pixels
a side. They are written here so the core package keeps numpy, pillow and shapely as its only dependencies.
"""

from __future__ import annotations

from typing import TypeVar

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from qipu_map.imageio import Pixels, array_mode

Mask = NDArray[np.bool_]
Floats = NDArray[np.floating]

N = TypeVar("N", bound=np.generic)


def _shift_max(a: NDArray[N], r: int, axis: int) -> NDArray[N]:
    """Each value becomes the largest of the 2r + 1 values around it along one axis; past the edge counts as nothing.

    The reach doubles each pass, so it takes log2(r) passes, not r.
    """
    out = a.copy()
    n = out.shape[axis]
    reach = 0
    while reach < r:
        step = min(reach + 1, r - reach)
        if step < n:
            src = out.copy()
            lo = [slice(None)] * out.ndim
            hi = [slice(None)] * out.ndim
            lo[axis], hi[axis] = slice(0, n - step), slice(step, n)
            np.maximum(out[tuple(hi)], src[tuple(lo)], out=out[tuple(hi)])
            np.maximum(out[tuple(lo)], src[tuple(hi)], out=out[tuple(lo)])
        reach += step
    return out


def max_filter(a: NDArray[N], r: int) -> NDArray[N]:
    """Each pixel becomes the largest value in the (2r + 1) square around it (grey dilation; spreads labels too)."""
    if r <= 0:
        return a.copy()
    return _shift_max(_shift_max(a, r, 0), r, 1)


def dilate(mask: Mask, r: int) -> Mask:
    """Grow a mask by r pixels (a (2r + 1) square)."""
    return max_filter(mask, r)


def erode(mask: Mask, r: int, *, edge_is_set: bool = True) -> Mask:
    """Shrink a mask by r pixels. With `edge_is_set`, pixels past the image's edge count as set, so a mask touching the
    edge is not eaten from it; without, the edge erodes like any other boundary."""
    if r <= 0:
        return mask.copy()
    if not edge_is_set:
        padded = np.pad(mask, r, mode="constant", constant_values=False)
        return erode(padded, r)[r:-r, r:-r]
    return ~dilate(~mask, r)


def opening(mask: Mask, r: int = 1) -> Mask:
    """Erode then dilate: drops specks and threads narrower than 2r + 1 pixels and keeps the rest's shape."""
    return dilate(erode(mask, r, edge_is_set=False), r)


def _float_like(a: NDArray[np.generic]) -> NDArray[np.floating]:
    """float64 stays float64; anything else becomes float32."""
    return a.astype(np.float64 if a.dtype == np.float64 else np.float32)


def box_blur(a: NDArray[np.generic], r: int) -> Floats:
    """Mean over a (2r + 1) square, edges replicated. Works on (h, w) and (h, w, c) arrays."""
    x = _float_like(a)
    if r <= 0:
        return x
    for axis in (0, 1):
        pad = [(0, 0)] * x.ndim
        pad[axis] = (r + 1, r)
        c = np.cumsum(np.pad(x, pad, mode="edge"), axis=axis, dtype=np.float64)
        n = x.shape[axis]
        hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
        lo = np.take(c, np.arange(0, n), axis=axis)
        x = ((hi - lo) / (2 * r + 1)).astype(x.dtype)
    return x


def gaussian(a: NDArray[np.generic], sigma: float) -> Floats:
    """A Gaussian blur, edges replicated: an exact separable kernel below sigma 3, three matched box blurs above.

    float64 input is blurred in float64, anything else in float32.
    """
    x = _float_like(a)
    if sigma >= 3.0:
        r = round((np.sqrt(4.0 * sigma * sigma + 1.0) - 1.0) / 2.0)
        for _ in range(3):
            x = box_blur(x, r)
        return x
    r = max(1, int(np.ceil(3.0 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k = (k / k.sum()).astype(x.dtype)
    for axis in (0, 1):
        pad = [(0, 0)] * x.ndim
        pad[axis] = (r, r)
        p = np.pad(x, pad, mode="edge")
        n = x.shape[axis]
        x = sum((w * np.take(p, np.arange(i, i + n), axis=axis) for i, w in enumerate(k)), np.zeros_like(x))
    return x


def blur_u8(image: Pixels, radius: float) -> Pixels:
    """Pillow's Gaussian blur of an 8-bit L, RGB or RGBA image, rounded back to 8 bits.

    The era stage's change thresholds were set on this blur, so it keeps it rather than the float `gaussian`.
    """
    im = Image.fromarray(np.ascontiguousarray(image), array_mode(image))
    out: Pixels = np.asarray(im.filter(ImageFilter.GaussianBlur(radius)))
    return out


def label(mask: Mask) -> tuple[NDArray[np.int32], int]:
    """4-connected components of a mask: (labels, count), labels 1..count in raster order of first pixel, 0 =
    background.

    Works on runs of set pixels per row and joins runs that overlap the row above, so the Python loop is over runs, not
    pixels.
    """
    h, _ = mask.shape
    parent: list[int] = [0]
    runs: list[tuple[int, int, int, int]] = []  # (row, start, stop, provisional label)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    prev: list[tuple[int, int, int]] = []
    for y in range(h):
        row = mask[y].astype(np.int8)
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row, [0]))))
        cur: list[tuple[int, int, int]] = []
        j = 0
        for s, e in zip(edges[0::2].tolist(), edges[1::2].tolist(), strict=True):
            lab = 0
            while j < len(prev) and prev[j][1] <= s:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] < e:
                other = find(prev[k][2])
                if lab == 0:
                    lab = other
                elif other != lab:
                    parent[max(lab, other)] = min(lab, other)
                    lab = min(lab, other)
                k += 1
            if lab == 0:
                lab = len(parent)
                parent.append(lab)
            cur.append((s, e, lab))
            runs.append((y, s, e, lab))
        prev = cur
    roots: dict[int, int] = {}
    out = np.zeros(mask.shape, np.int32)
    for y, s, e, lab in runs:
        root = find(lab)
        out[y, s:e] = roots.setdefault(root, len(roots) + 1)
    return out, len(roots)


def to_rgba(image: Pixels) -> Pixels:
    """An RGB or RGBA image as RGBA; RGB becomes fully opaque."""
    if image.ndim == 3 and image.shape[2] == 4:
        return image
    if image.ndim == 3 and image.shape[2] == 3:
        return np.dstack([image, np.full(image.shape[:2], 255, np.uint8)])
    raise ValueError(f"expected an RGB or RGBA image, got shape {image.shape}")


def halve_rgba(image: Pixels) -> Pixels:
    """Halve an RGBA image with a 2 x 2 box filter on premultiplied colour, padding an odd edge with transparency.

    Averaging straight colour lets the black of transparent pixels bleed into the edge of what is painted (a dark
    fringe around the city and around every hole); weighting each pixel's colour by its alpha avoids it.
    """
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError(f"halve_rgba needs an (h, w, 4) image, got {image.shape}")
    h, w = image.shape[:2]
    padded = np.pad(image, [(0, h % 2), (0, w % 2), (0, 0)], constant_values=0) if h % 2 or w % 2 else image
    rgba = padded.astype(np.float32)
    alpha = rgba[..., 3:4] / 255.0
    premul = np.concatenate([rgba[..., :3] * alpha, rgba[..., 3:4]], axis=2)
    small = premul.reshape(padded.shape[0] // 2, 2, padded.shape[1] // 2, 2, 4).mean(axis=(1, 3))
    out_alpha = small[..., 3:4] / 255.0
    rgb = np.divide(small[..., :3], out_alpha, out=np.zeros_like(small[..., :3]), where=out_alpha > 0)
    return np.clip(np.rint(np.concatenate([rgb, small[..., 3:4]], axis=2)), 0, 255).astype(np.uint8)
