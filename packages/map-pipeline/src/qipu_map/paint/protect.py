"""Protected surfaces: what the painted canvas takes back from the render.

- Water. The render's water is the map's water: the model invents land in bays and ponds on lots, and the eras need
  water that only changes where the shoreline did.
- Anything standing in the water that the class pass does not call land: boats, wakes, floats, a bridge deck. A
  straight ferry wake left to the model became a pier lined with houses. A patch counts when at least 85 % of the ring
  around it is water.
- Optionally a `keep` mask the caller supplies (big glass towers on the old recipe, which the model makes see-through).

The edge is soft: a 1 px Gaussian rim blends the render up to half way into the painting beside the water, so the shore
does not look cut out.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass as C
from qipu_map.imageops import gaussian, label, max_filter

RGB = NDArray[np.uint8]
Mask = NDArray[np.bool_]

ON_WATER_RING = 8
ON_WATER_SHARE = 0.85
ON_WATER_MAX_PX = 100_000  # about 6,000 m2 at 0.25 m/px: boats, wakes and floats, never an island


def on_water(classes: NDArray[np.uint8]) -> Mask:
    """Patches that are not water but stand inside it: at least 85 % of an 8 px ring around them is water."""
    water = classes == C.WATER
    labels, n = label(~water)
    if n == 0:
        return np.zeros(classes.shape, bool)
    near = max_filter(labels, ON_WATER_RING)
    ring = near != labels  # pixels within reach of a patch but outside it, counted for that patch
    total = np.bincount(near[ring], minlength=n + 1)
    wet = np.bincount(near[ring & water], minlength=n + 1)
    share = wet / np.maximum(total, 1)
    touches_border = np.zeros(n + 1, bool)
    for edge in (labels[0], labels[-1], labels[:, 0], labels[:, -1]):
        touches_border[np.unique(edge)] = True
    small = np.bincount(labels.ravel(), minlength=n + 1) <= ON_WATER_MAX_PX
    keep = (share >= ON_WATER_SHARE) & small & ~touches_border
    keep[0] = False
    out: Mask = keep[labels]
    return out


def protect(painted: RGB, render: RGB, classes: NDArray[np.uint8], keep: Mask | None = None) -> RGB:
    water = classes == C.WATER
    hard = water | on_water(classes)
    if keep is not None:
        hard |= keep
    rim = gaussian(water.astype(np.float32), 0.8)
    alpha = np.where(hard, 1.0, np.minimum(rim, 0.5) * (rim > 0.05)).astype(np.float32)[..., None]
    out: RGB = np.clip(painted * (1.0 - alpha) + render * alpha + 0.5, 0, 255).astype(np.uint8)
    return out
