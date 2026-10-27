"""Guards: catch a painted tile that lost a building or invented one, so it can be re-rolled.

Both compare the painted tile with the render tile and its class pass, and both target one specific defect; neither
pulls the tile's overall look toward the render, because a guard that does takes the painted look away.

- vanish: a building the render shows that the painting dissolved into its surroundings. Per building (a connected
  patch of roof and wall), the colour contrast between the building and an 8 px ring around it, in the render and in the
  painting. A building with a clear contrast in the render (at least 12 in Lab) that keeps less than a third of it in
  the painting counts with its area.
- invent: roof-like painted blobs on open ground or water, far from any render building (mansions on a seaside
  meadow, a pier of houses along a ferry wake). The rule: painted pixels of low chroma, not green and far from the
  render's colour, where the render is chromatic (grass, leaves, sand, sea; a repainted grey lot
  is not a house), grouped into blobs at least 4,000 px big and 14 px thick, whose edges mostly run in two perpendicular
  directions, as a building's do (a row of driftwood logs is thin, a texture has no main direction).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass as C
from qipu_map.imageops import dilate, erode, gaussian, label, max_filter
from qipu_map.paint.colour import chroma, rgb_to_lab

RGB = NDArray[np.uint8]

BUILDING = (C.ROOF, C.WALL)
OPEN = (C.GROUND, C.GRASS, C.TREE, C.SAND, C.WATER)

# Sizes are in pixels of a 1024 px tile; colour distances and chroma are in Lab.
VANISH_MIN_AREA = 2000  # smaller patches are sheds and roof details, whose loss does not change the map
VANISH_RING = 8  # the band around a building it is compared with
VANISH_CONTRAST = 12.0  # a building the render barely sets apart cannot be said to have vanished
VANISH_KEEP = 1 / 3  # keeping less than this share of the render's contrast is dissolving the building

INVENT_BUF = 24  # blobs this close to a render building may be that building drawn a little larger
INVENT_DE = 18.0  # the painting must have changed the colour there, not only its tone
INVENT_CHMAX = 18.0  # roofs and pale walls are greyish; grass, leaves, sand and sea are not
INVENT_LMIN = 35.0  # darker is deep shadow
INVENT_LMAX = 185.0  # lighter is glare, foam or a white sand bank
INVENT_RCH = 10.0  # only where the render is coloured: a grey lot painted as a grey house is not an invention
INVENT_AMIN = 4000  # about the size of a house at this scale
INVENT_RMIN = 14  # a blob must be this thick: a row of driftwood logs, a path or a wake is thinner
INVENT_EDGE = 0.30  # share of edge energy along two perpendicular directions; a texture scores about 1/6
EDGE_MIN = 20.0  # weaker gradients are paint texture, not edges
SOBEL_GAIN = 8.0  # the thresholds were set on a 3x3 Sobel, which reads about 8 times the per-pixel gradient
# The invent thresholds were tuned on OpenCV's 8-bit Lab, whose lightness runs 0-255 (L* x 2.55); `_cv_lab` puts the
# image on that scale so the numbers keep their meaning.
CV_L_SCALE = 255.0 / 100.0

# Area (px) of vanished or invented buildings that flags a tile for a re-roll.
THRESHOLDS = {"vanish": 3000, "invent": 12000}


@dataclass(frozen=True)
class Verdict:
    scores: dict[str, int]

    @property
    def flags(self) -> list[str]:
        return sorted(k for k, th in THRESHOLDS.items() if self.scores.get(k, 0) >= th)

    @property
    def cost(self) -> float:
        """Lower is better; how a re-roll is chosen among the candidates."""
        return sum(min(3.0, self.scores.get(k, 0) / th) for k, th in THRESHOLDS.items())


def judge(painted: RGB, render: RGB, classes: NDArray[np.uint8]) -> Verdict:
    """Compare a painted tile with its render and class pass and score the defects: area in pixels of vanished and of
    invented buildings."""
    lp, lr = rgb_to_lab(painted), rgb_to_lab(render)
    return Verdict(
        {"vanish": vanished(lp, lr, classes), "invent": invented(painted, _cv_lab(lp), _cv_lab(lr), classes)}
    )


def _cv_lab(lab: NDArray[np.float32]) -> NDArray[np.float32]:
    out = lab.copy()
    out[..., 0] *= CV_L_SCALE
    return out


def _green(rgb: RGB) -> NDArray[np.bool_]:
    a = rgb.astype(np.int16)
    out: NDArray[np.bool_] = (a[..., 1] > a[..., 0] + 3) & (a[..., 1] > a[..., 2] - 6)
    return out


def vanished(lp: NDArray[np.float32], lr: NDArray[np.float32], classes: NDArray[np.uint8]) -> int:
    """Total area (px) of render buildings the painting dissolved."""
    bld = np.isin(classes, BUILDING)
    labels, n = label(bld)
    if n == 0:
        return 0
    ring = max_filter(labels, VANISH_RING)
    ring[bld] = 0
    area = np.bincount(labels.ravel(), minlength=n + 1).astype(np.float64)
    ring_n = np.bincount(ring.ravel(), minlength=n + 1).astype(np.float64)

    def contrast(lab: NDArray[np.float32]) -> NDArray[np.float64]:
        diff = np.zeros(n + 1)
        means_in, means_out = [], []
        for ch in range(3):
            means_in.append(np.bincount(labels.ravel(), lab[..., ch].ravel(), n + 1) / np.maximum(area, 1))
            means_out.append(np.bincount(ring.ravel(), lab[..., ch].ravel(), n + 1) / np.maximum(ring_n, 1))
        for a, b in zip(means_in, means_out, strict=True):
            diff += (a - b) ** 2
        out: NDArray[np.float64] = np.sqrt(diff)
        return out

    cr, cp = contrast(lr), contrast(lp)
    gone = (area >= VANISH_MIN_AREA) & (ring_n > 0) & (cr >= VANISH_CONTRAST) & (cp < VANISH_KEEP * cr)
    gone[0] = False
    return int(area[gone].sum())


def invented(painted: RGB, lp: NDArray[np.float32], lr: NDArray[np.float32], classes: NDArray[np.uint8]) -> int:
    """Total area (px) of roof-like blobs the painting put on open ground or water. `lp` and `lr` are on OpenCV's Lab
    scale (see `CV_L_SCALE`)."""
    built = ~np.isin(classes, OPEN)
    zone = np.isin(classes, OPEN) & ~dilate(built, INVENT_BUF)
    if zone.sum() < INVENT_AMIN:
        return 0
    de = np.sqrt(((lp - lr) ** 2).sum(-1))
    cand = (
        zone
        & (chroma(lr) >= INVENT_RCH)
        & (de > INVENT_DE)
        & ~_green(painted)
        & (chroma(lp) < INVENT_CHMAX)
        & (lp[..., 0] > INVENT_LMIN)
        & (lp[..., 0] < INVENT_LMAX)
    )
    cand = dilate(erode(erode(dilate(cand, 4), 4), 4), 4)  # close, then open: join a roof's pieces, drop specks
    labels, n = label(cand)
    if n == 0:
        return 0
    area = np.bincount(labels.ravel(), minlength=n + 1)
    thick = np.zeros(n + 1, bool)
    thick[np.unique(labels[erode(cand, INVENT_RMIN)])] = True
    keep = (area >= INVENT_AMIN) & thick
    keep[0] = False
    if not keep.any():
        return 0
    coh = _edge_coherence(lp[..., 0], max_filter(labels, 3), n)
    keep &= coh >= INVENT_EDGE
    return int(area[keep].sum())


def _edge_coherence(lum: NDArray[np.float32], labels: NDArray[np.int32], n: int) -> NDArray[np.float64]:
    """Per label, the share of edge energy within +-7.5 degrees of one direction or its normal (1/6 for a texture)."""
    g = gaussian(lum, 1.0)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy) * SOBEL_GAIN
    bins = (np.degrees(np.arctan2(gy, gx)) % 90.0 / 5.0).astype(np.int64) % 18
    w = np.where(mag > EDGE_MIN, mag, 0.0)
    hist = np.bincount((labels.astype(np.int64) * 18 + bins).ravel(), w.ravel(), (n + 1) * 18).reshape(n + 1, 18)
    h3 = hist + np.roll(hist, 1, axis=1) + np.roll(hist, -1, axis=1)
    out: NDArray[np.float64] = h3.max(1) / np.maximum(hist.sum(1), 1e-6)
    return out
