"""The past-year layer: a painted year where it differs from today, transparent where it looks like today.

The viewer draws it over today's map, so the past costs bytes only where it differs. Where the past year is water and
today is water too, the layer is transparent and today's own water shows. Painted water from two runs never has the same
tone, and would show as boxes of slightly different blue.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass
from qipu_map.eras.compare import changed_mask
from qipu_map.imageio import Pixels
from qipu_map.imageops import blur_u8, to_rgba

FEATHER_PX = 2.0


def past_layer(
    painted: NDArray[np.uint8],
    today: NDArray[np.uint8],
    classes: NDArray[np.uint8],
    today_classes: NDArray[np.uint8],
    feather_px: float = FEATHER_PX,
) -> Pixels:
    """The RGBA layer of one past year.

    `painted` and `today` are the painted canvases (RGB or RGBA), `classes` and `today_classes` the render's class
    passes (`classes.SurfaceClass` ids). Alpha is 255 inside the changed area, eased to 0 at its edge over `feather_px`,
    and exactly 0 everywhere else; colour is 0 where alpha is 0.
    """
    p4 = to_rgba(painted)
    if classes.shape != p4.shape[:2] or today_classes.shape != p4.shape[:2]:
        raise ValueError("the class passes must have the canvas's size")
    keep = changed_mask(p4, today) & (p4[..., 3] >= 128)
    keep &= ~((classes == SurfaceClass.WATER) & (today_classes == SurfaceClass.WATER))
    alpha = _feather_inside(keep, feather_px)
    rgb = np.where(alpha[..., None] > 0, p4[..., :3], 0).astype(np.uint8)
    return np.dstack([rgb, alpha])


def _feather_inside(mask: NDArray[np.bool_], radius: float) -> NDArray[np.uint8]:
    """A soft edge that only fades inward: pixels outside the mask stay exactly 0."""
    soft = blur_u8(mask.astype(np.uint8) * 255, radius)
    out: NDArray[np.uint8] = np.where(mask, soft, 0).astype(np.uint8)
    return out
