"""Trees: the City's street-tree register, and the crowns the LiDAR sees everywhere else (yards, parks, woods).

Street trees keep the register's height; their crown comes from the trunk's diameter (a + b·DBH). Canopy crowns: heights
above ground over 2.5 m that are not on a building, smoothed, their local maxima as tree tops (the search window grows
with the height), and each crown's width from the canopy cells nearest to its top. A crown within 2.5 m of a register
tree is that tree and is not added twice.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.imageops import gaussian, max_filter, opening
from qipu_map.model import Raster, Tree, TreeForm

CANOPY_MIN_M = 2.5  # lower than this is shrubs, hedges, cars
PEAK_WINDOWS = ((0.0, 8.0, 3), (8.0, 16.0, 5), (16.0, 25.0, 7), (25.0, 99.0, 9))  # (from, to height m, window cells)
MIN_CROWN_CELLS = 4
SAME_TREE_M = 2.5
DEFAULT_HEIGHT_M = 8.0

_CONIFERS = re.compile(
    r"^(pinus|picea|abies|pseudotsuga|thuja|tsuga|larix|cedrus|chamaecyparis|cupressus|sequoia|sequoiadendron|"
    r"metasequoia|taxus|juniperus|calocedrus|callitropsis|cryptomeria|araucaria|cupressocyparis|xcupressocyparis)\b"
)
_PALMS = re.compile(r"^(trachycarpus|phoenix|washingtonia|butia|chamaerops)\b")
# Crown width (m) from the trunk's diameter at breast height (inches): a + b·DBH, at most c, with the values used for
# Vancouver.
_CROWN_DBH: dict[TreeForm, tuple[float, float, float]] = {
    TreeForm.BROADLEAF: (2.0, 0.38, 16.0),
    TreeForm.CONIFER: (2.0, 0.24, 12.0),
    TreeForm.PALM: (3.0, 0.0, 3.0),
}


def form_of(genus: str | None) -> TreeForm:
    g = (genus or "").strip().lower()
    if _CONIFERS.match(g):
        return TreeForm.CONIFER
    if _PALMS.match(g):
        return TreeForm.PALM
    return TreeForm.BROADLEAF


def crown_width(form: TreeForm, diameter_cm: float | None, height_m: float) -> float:
    """From the trunk when the register measured it, else from the height (a broadleaf about 60 % as wide as tall)."""
    a, b, cap = _CROWN_DBH[form]
    if diameter_cm and diameter_cm > 0:
        return round(min(cap, a + b * diameter_cm / 2.54), 2)
    share = {TreeForm.BROADLEAF: 0.6, TreeForm.CONIFER: 0.35, TreeForm.PALM: 0.3}[form]
    return round(min(cap, max(a, share * height_m)), 2)


@dataclass(frozen=True)
class Listed:
    """A register tree, already in local metres."""

    id: str
    x: float
    y: float
    genus: str | None
    height_m: float | None
    diameter_cm: float | None
    year_planted: int | None


def street_tree(t: Listed) -> Tree:
    form = form_of(t.genus)
    h = t.height_m if t.height_m and t.height_m > 0 else DEFAULT_HEIGHT_M
    return Tree(t.id, t.x, t.y, round(h, 2), crown_width(form, t.diameter_cm, h), form, t.genus, t.year_planted)


def canopy(height: Raster, buildings: NDArray[np.bool_], listed: list[Tree]) -> list[Tree]:
    """Crowns from a height-above-ground raster. `buildings` marks the cells on a footprint (grown by a cell)."""
    h = np.where(np.isfinite(height.data), np.clip(height.data, 0.0, 80.0), 0.0).astype(np.float64)
    mask = opening((h > CANOPY_MIN_M) & ~buildings)  # drops lamp posts and wires, keeps crowns
    smooth = gaussian(np.where(mask, h, 0.0), 1.0)
    peaks = np.zeros_like(mask)
    for lo, hi, size in PEAK_WINDOWS:
        peaks |= (smooth >= max_filter(smooth, size // 2)) & (smooth >= lo) & (smooth < hi)
    peaks &= mask & (smooth > CANOPY_MIN_M)
    pi, pj = _one_per_top(peaks, smooth)
    if pi.size == 0:
        return []
    owner = _nearest_peak(np.argwhere(mask), np.column_stack([pi, pj]))
    cells = np.bincount(owner, minlength=pi.size)
    tops = np.zeros(pi.size)
    np.maximum.at(tops, owner, h[mask])
    taken = shapely.STRtree([shapely.Point(t.x, t.y) for t in listed]) if listed else None
    out = []
    for k in range(pi.size):
        x = float(height.x0 + (pj[k] + 0.5) * height.cell)
        y = float(height.y0 - (pi[k] + 0.5) * height.cell)
        if cells[k] < MIN_CROWN_CELLS:
            continue
        if taken is not None and taken.query(shapely.Point(x, y), predicate="dwithin", distance=SAME_TREE_M).size:
            continue
        crown = 2 * math.sqrt(cells[k] * height.cell**2 / math.pi)
        out.append(
            Tree(
                f"canopy-{round(x)}-{round(y)}",
                round(x, 2),
                round(y, 2),
                round(float(tops[k]), 2),
                round(crown, 2),
                _canopy_form(tops[k], crown),
            )
        )
    return out


def _one_per_top(peaks: NDArray[np.bool_], smooth: NDArray[np.floating]) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    """One cell per tree top: a flat top spans several equal cells, and the highest (then the first) one stands for
    it."""
    pi, pj = np.nonzero(peaks)
    order = np.lexsort((pj, pi, -smooth[pi, pj]))
    claimed = np.zeros(peaks.shape, dtype=bool)
    keep = []
    for k in order:
        i, j = pi[k], pj[k]
        if not claimed[i, j]:
            keep.append(k)
            claimed[max(0, i - 1) : i + 2, max(0, j - 1) : j + 2] = True
    kept = np.array(sorted(keep), dtype=np.intp)
    return pi[kept], pj[kept]


def _canopy_form(top: float, crown: float) -> TreeForm:
    """A crown much taller than it is wide reads as a conifer (the LiDAR alone cannot tell leaf from needle)."""
    return TreeForm.CONIFER if top > 2.2 * crown else TreeForm.BROADLEAF


def _nearest_peak(cells: NDArray[np.intp], peaks: NDArray[np.intp]) -> NDArray[np.intp]:
    tree = shapely.STRtree([shapely.Point(float(i), float(j)) for i, j in peaks])
    idx = tree.query_nearest(shapely.points(cells.astype(np.float64)), all_matches=False)
    owner = np.empty(len(cells), dtype=np.intp)
    owner[idx[0]] = idx[1]
    return owner
