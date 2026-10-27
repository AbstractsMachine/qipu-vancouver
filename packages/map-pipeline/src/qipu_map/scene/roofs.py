"""A roof's form, flat, gable or hip, read from the LiDAR surface over the footprint.

From the 1 m surface grid, without the point cloud: per 1 m cell the surface's slope; cells on a step (an edge, a
parapet, the ridge line, a tree) are left out. Mostly level cells make a flat roof. Otherwise three roof models are
fitted on the footprint's minimum-area rectangle (a gable along the long side, a gable across it, a hip) and the
closest one wins; a hip has to beat the better gable clearly, because at 1 m a house's roof faces are 3 to 5 cells
wide and the two are easy to confuse. When the reading cannot be trusted the answer is None and the type decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.model import Raster, RoofForm
from qipu_map.scene.pixels import inset, inside, window

INSET_M = 0.5
MIN_CELLS = 20
MAX_VOID = 0.35
STEP_M = 0.45  # a cell this far from the mean of its 8 neighbours sits on a step
LEVEL_DEG, PITCH_MIN_DEG, PITCH_MAX_DEG = 9.0, 14.0, 62.0
LEVEL_SHARE = 0.45  # flat when this share of the kept cells is level, or less than this share is pitched
HIP_RATIO = 0.85  # a hip must fit at least this much better than the better gable
LOW_LEVEL_SHARE, LOW_RATIO, LOW_MIN_DEG = 0.6, 0.5, 8.0  # the 1960s-80s houses' low pitches read mostly as level
SHED_RATIO = 0.8
SLIDE_M = (-1.0, -0.5, 0.0, 0.5, 1.0)  # footprints and survey are years apart: let the ridge slide


@dataclass(frozen=True)
class RoofFit:
    form: RoofForm
    pitch_deg: float
    ridge_across: bool = False  # a gable whose ridge runs across the footprint's long side


@dataclass(frozen=True)
class _Fit:
    residual: float  # median absolute residual (m)
    slope: float  # rise per metre


def classify(footprint: shapely.Polygon, dsm: Raster) -> RoofFit | None:
    poly = inset(footprint, INSET_M)
    win = window(dsm, poly.bounds, margin=1)
    if win.values.size == 0:
        return None
    mask = inside(win, poly)
    z = win.values.astype(np.float64)
    n = int(mask.sum())
    if n < MIN_CELLS or float(np.mean(~np.isfinite(z[mask]))) > MAX_VOID:
        return None
    slope, smooth = _slope(z, win.cell)
    keep = mask & smooth
    if keep.sum() < 10:
        return None
    s = slope[keep]
    level, pitched = float(np.mean(s < LEVEL_DEG)), float(np.mean((s >= PITCH_MIN_DEG) & (s <= PITCH_MAX_DEG)))
    gx, gy = win.centres()
    finite = mask & np.isfinite(z)
    fits = _fit_models(gx[finite], gy[finite], z[finite], footprint)
    if pitched < LEVEL_SHARE or level > LEVEL_SHARE:
        best = _best_pitched(fits)
        low_pitch = (
            best is not None and level < LOW_LEVEL_SHARE and fits[best].residual < LOW_RATIO * fits["flat"].residual
        )
        if not (low_pitch and best is not None and fits[best].slope > math.tan(math.radians(LOW_MIN_DEG))):
            return RoofFit(RoofForm.FLAT, 0.0)
    return _decide(fits)


def _slope(z: NDArray[np.float64], cell: float) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    """Slope in degrees per cell, and whether the cell is off any step."""
    gy, gx = np.gradient(z, cell)
    padded = np.pad(z, 1, mode="edge")
    h, w = z.shape
    ring = [padded[1 + di : 1 + di + h, 1 + dj : 1 + dj + w] for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]
    with np.errstate(invalid="ignore"):
        step = np.abs(z - np.mean(ring, axis=0))
        smooth = np.isfinite(gx) & np.isfinite(gy) & (np.nan_to_num(step, nan=9.0) < STEP_M)
    return np.degrees(np.arctan(np.hypot(np.nan_to_num(gx), np.nan_to_num(gy)))), smooth


def _fit_models(
    x: NDArray[np.float64], y: NDArray[np.float64], z: NDArray[np.float64], footprint: shapely.Polygon
) -> dict[str, _Fit]:
    """Fits of z = eave + k * d(p), d the distance to the eave line, for each roof model; and a level plane."""
    out = {"flat": _Fit(float(np.median(np.abs(z - np.median(z)))), 0.0)}
    if z.size < 8:
        return out
    cx, cy, theta, half_long, half_short = _rectangle(footprint)
    a = (x - cx) * math.cos(theta) + (y - cy) * math.sin(theta)
    b = -(x - cx) * math.sin(theta) + (y - cy) * math.cos(theta)
    one = np.ones_like(z)
    plane = _trimmed_fit(np.stack([one, a, b], 1), z)
    if plane:
        out["plane"] = _Fit(plane[1], float(math.hypot(plane[0][1], plane[0][2])))
    for model in ("gable_long", "gable_across", "hip"):
        best: _Fit | None = None
        for o1 in SLIDE_M:
            for o2 in SLIDE_M if model == "hip" else (0.0,):
                if model == "gable_long":
                    d = half_short - np.abs(b - o1)
                elif model == "gable_across":
                    d = half_long - np.abs(a - o1)
                else:
                    d = np.minimum(half_short - np.abs(b - o1), half_long - np.abs(a - o2))
                f = _trimmed_fit(np.stack([one, d], 1), z)
                if f and f[0][1] > 0 and (best is None or f[1] < best.residual):
                    best = _Fit(f[1], float(f[0][1]))
        if best:
            out[model] = best
    return out


def _trimmed_fit(design: NDArray[np.float64], z: NDArray[np.float64]) -> tuple[NDArray[np.float64], float] | None:
    """Least squares, refitted twice without the cells far off the fit (chimneys, a branch over the roof)."""
    keep = np.ones(len(z), dtype=bool)
    sol = np.zeros(design.shape[1])
    for _ in range(3):
        if keep.sum() < 8:
            return None
        sol = np.linalg.lstsq(design[keep], z[keep], rcond=None)[0]
        r = z - design @ sol
        keep = np.abs(r) < max(0.2, 2.5 * float(np.sqrt(np.mean(r[keep] ** 2))))
    return sol, float(np.median(np.abs(z - design @ sol)))


def _best_pitched(fits: dict[str, _Fit]) -> str | None:
    models = [m for m in ("gable_long", "gable_across", "hip") if m in fits]
    return min(models, key=lambda m: fits[m].residual) if models else None


def _decide(fits: dict[str, _Fit]) -> RoofFit | None:
    best = _best_pitched(fits)
    if best is None:
        return None
    plane = fits.get("plane")
    if plane and plane.slope > math.tan(math.radians(10)) and plane.residual < SHED_RATIO * fits[best].residual:
        return None  # one sloping plane: a shed roof, which the scene has no form for
    gables = [m for m in ("gable_long", "gable_across") if m in fits]
    if "hip" in fits and (not gables or fits["hip"].residual < HIP_RATIO * min(fits[g].residual for g in gables)):
        return RoofFit(RoofForm.HIP, math.degrees(math.atan(fits["hip"].slope)))
    g = min(gables, key=lambda m: fits[m].residual)
    return RoofFit(RoofForm.GABLE, math.degrees(math.atan(fits[g].slope)), ridge_across=g == "gable_across")


def _rectangle(footprint: shapely.Polygon) -> tuple[float, float, float, float, float]:
    """The minimum-area rectangle: centre, the long side's direction, half its length and half its width."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rect = shapely.minimum_rotated_rectangle(footprint)
    c = shapely.get_coordinates(rect)[:4]
    e1, e2 = c[1] - c[0], c[2] - c[1]
    l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
    long_side = e1 if l1 >= l2 else e2
    centre = c.mean(axis=0)
    return (
        float(centre[0]),
        float(centre[1]),
        math.atan2(float(long_side[1]), float(long_side[0])),
        max(l1, l2) / 2,
        min(l1, l2) / 2,
    )
