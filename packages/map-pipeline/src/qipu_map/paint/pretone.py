"""Pre-toning: small colour fixes to the render before the model sees it. The pre-toned image is the model's input only;
it is never shown.

Each fix answers something the model was seen to invent:

- flat blue reads as water. Sky-lit asphalt and shadows on flat dry ground come out of the renderer blue (b* -7 to -12),
  like its water, and the model painted streets as canals and a lot's shadow as a pond. Streets, sidewalks and dry
  ground more than 40 px from water get their b* raised to at least -1.
- grey roofs next to the sea carry the same sky-blue cast and were painted as sea. Low-chroma roofs (C* < 12) get b*
  raised to at least +1.
- a street needs grain to read as asphalt: a light L* noise, seeded by the world 64 px cell so it has no seams and is
the
  same in every run.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass as C
from qipu_map.imageops import dilate, gaussian
from qipu_map.paint.colour import chroma, lab_to_rgb, rgb_to_lab

RGB = NDArray[np.uint8]

NEAR_WATER_PX = 40  # ground this close to water may be shore, which is allowed to look like water
GROUND_MIN_B = -1.0  # b* floor for streets and dry ground: just short of neutral, so they stop reading blue
GREY_ROOF_CHROMA = 12.0  # roofs below this chroma count as grey
GREY_ROOF_MIN_B = 1.0  # b* floor for grey roofs: a touch warm, so they stop reading as sea
SOFT_EDGE_PX = 1.5  # each fix fades in over this blur, so it leaves no hard class edge in the image
GRAIN = 2.5  # sd of the street grain before blurring, in L*
GRAIN_CELL = 64  # the grain is seeded per world cell of this many pixels
GRAIN_BLUR_PX = 0.7  # the grain is softened to the size of asphalt texture
GRAIN_GAIN = 2.0  # the blur keeps about 40 % of the grain's spread; doubling it gives about 2 L* of grain


def pretone(rgb: RGB, classes: NDArray[np.uint8], origin: tuple[int, int] = (0, 0)) -> RGB:
    """`origin` is the image's top-left in world pixels, which keys the street grain."""
    lab = rgb_to_lab(rgb)
    near_water = dilate(classes == C.WATER, NEAR_WATER_PX)
    flat = np.isin(classes, [C.ROAD, C.SIDEWALK]) | (np.isin(classes, [C.GROUND, C.NONE]) & ~near_water)
    soft = gaussian(flat.astype(np.float32), SOFT_EDGE_PX)
    lab[..., 2] += np.maximum(0.0, GROUND_MIN_B - lab[..., 2]) * soft

    grey_roof = (classes == C.ROOF) & (chroma(lab) < GREY_ROOF_CHROMA)
    soft = gaussian(grey_roof.astype(np.float32), SOFT_EDGE_PX)
    lab[..., 2] += np.maximum(0.0, GREY_ROOF_MIN_B - lab[..., 2]) * soft

    street = gaussian((classes == C.ROAD).astype(np.float32), SOFT_EDGE_PX)
    noise = gaussian(grain(origin, rgb.shape[1], rgb.shape[0]), GRAIN_BLUR_PX)
    lab[..., 0] += noise * GRAIN_GAIN * street
    return lab_to_rgb(lab)


def grain(origin: tuple[int, int], width: int, height: int) -> NDArray[np.float32]:
    """Gaussian noise (sd GRAIN) whose 64 px cells are seeded by their world cell index."""
    ox, oy = origin
    out = np.empty((height, width), np.float32)
    for cy in range(oy // GRAIN_CELL, (oy + height - 1) // GRAIN_CELL + 1):
        for cx in range(ox // GRAIN_CELL, (ox + width - 1) // GRAIN_CELL + 1):
            seed = (cy * 100_003 + cx) & 0xFFFF_FFFF_FFFF
            cell = np.random.default_rng(seed).normal(0.0, GRAIN, (GRAIN_CELL, GRAIN_CELL)).astype(np.float32)
            ax, ay = cx * GRAIN_CELL, cy * GRAIN_CELL
            x0, y0 = max(ax, ox), max(ay, oy)
            x1, y1 = min(ax + GRAIN_CELL, ox + width), min(ay + GRAIN_CELL, oy + height)
            out[y0 - oy : y1 - oy, x0 - ox : x1 - ox] = cell[y0 - ay : y1 - ay, x0 - ax : x1 - ax]
    return out
