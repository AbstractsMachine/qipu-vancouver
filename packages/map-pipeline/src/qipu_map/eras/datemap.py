"""Date maps: for each canvas pixel, the date it switches from one era year to the next.

For a segment A to B, per pixel:
- a pixel showing a building that appears or goes in the segment takes that building's date, over its whole footprint
  and walls, whether or not the painting changed there;
- a changed pixel within 12 px of such a building (its shadow, its lot) takes the nearest building's date;
- any other changed pixel gets a date from a smooth noise field spread over the segment (ground, roads, paint);
- an unchanged pixel never switches.

The noise is bilinear between random values on a coarse grid: hashed blocks of pixels would show during playback as
rectangles switching tone, and smooth cells have no edges. The grid is fixed to world pixels, not to the canvas, so two
neighbouring areas date their shared ground alike.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from qipu_map.eras.years import switch_date
from qipu_map.hashing import stable_seed
from qipu_map.model import Building

HALO_PX = 12
DISSOLVE_CELL_PX = 64
_CHUNK = 16  # noise grid points per side drawn from one generator

Dates = NDArray[np.float64]


def segment_building_dates(
    a_buildings: Sequence[Building], b_buildings: Sequence[Building], a: int, b: int
) -> tuple[Dates, Dates]:
    """Per building of each scene (index 0 = no building), the date it switches in the segment, NaN if it does not.

    A building of scene A that scene B lacks goes at its demolition date; one of scene B that A lacks appears at its
    year built. Buildings in both scenes do not switch, and one whose record date falls outside the segment (removed by
    a convention rather than a record) gets NaN: its pixels are spread with the ground.
    """
    in_a = {x.id for x in a_buildings}
    in_b = {x.id for x in b_buildings}
    da = np.full(len(a_buildings) + 1, np.nan)
    db = np.full(len(b_buildings) + 1, np.nan)
    for i, x in enumerate(a_buildings, 1):
        if x.id not in in_b:
            da[i] = _nan(switch_date(x.demolished, x.id, a, b))
    for i, x in enumerate(b_buildings, 1):
        if x.id not in in_a:
            db[i] = _nan(switch_date(x.year_built, x.id, a, b))
    return da, db


def _nan(v: float | None) -> float:
    return np.nan if v is None else v


def building_pixels(ids_a: NDArray[np.int64], ids_b: NDArray[np.int64], dates_a: Dates, dates_b: Dates) -> Dates:
    """Per pixel, the earliest switch date of the building shown there in A or in B (NaN where neither switches)."""
    for ids, dates in ((ids_a, dates_a), (ids_b, dates_b)):
        if ids.size and (int(np.max(ids)) >= len(dates) or int(np.min(ids)) < 0):
            raise ValueError("the id pass names a building the scene does not have: was it rendered from this scene?")
    out: Dates = np.fmin(dates_a[ids_a], dates_b[ids_b])
    return out


def _disk_offsets(radius: int) -> list[tuple[int, int]]:
    r = range(-radius, radius + 1)
    pts = [(dy, dx) for dy in r for dx in r if 0 < dy * dy + dx * dx <= radius * radius]
    return sorted(pts, key=lambda p: (p[0] * p[0] + p[1] * p[1], p[0], p[1]))


def halo(dates: Dates, where: NDArray[np.bool_], radius: int = HALO_PX) -> Dates:
    """For the pixels in `where` that have no date, the date of the nearest dated pixel within `radius` (else NaN).

    Offsets are tried nearest first, with a fixed order for equal distances, so the result is deterministic.
    """
    h, w = dates.shape
    has = ~np.isnan(dates)
    out = np.full(dates.shape, np.nan)
    todo = where & ~has
    for dy, dx in _disk_offsets(radius):
        if not todo.any():
            break
        ys, yd = slice(max(dy, 0), h + min(dy, 0)), slice(max(-dy, 0), h - max(dy, 0))
        xs, xd = slice(max(dx, 0), w + min(dx, 0)), slice(max(-dx, 0), w - max(dx, 0))
        take = todo[yd, xd] & has[ys, xs]
        out[yd, xd][take] = dates[ys, xs][take]
        todo[yd, xd] &= ~take
    return out


def dissolve(
    shape: tuple[int, int],
    a: int,
    b: int,
    *,
    cell_px: int = DISSOLVE_CELL_PX,
    seed: int = 0,
    origin: tuple[int, int] = (0, 0),
) -> Dates:
    """A smooth date field over a canvas whose top-left is world pixel `origin`, every value within 10 % and 90 % of
    the segment.

    Random values on a world grid of `cell_px` cells, interpolated bilinearly. Each block of grid points is drawn from
    a generator seeded by the segment and the block's place, so a place gets the same date in every run and every area.
    """
    h, w = shape
    ry, ty = _axis(origin[1], h, cell_px)
    rx, tx = _axis(origin[0], w, cell_px)
    grid = _grid(int(rx[0]), int(ry[0]), int(rx[-1]) + 2, int(ry[-1]) + 2, f"{seed}:{a}-{b}")
    ry, rx = ry - ry[0], rx - rx[0]
    rows = grid[ry] * (1 - ty)[:, None] + grid[ry + 1] * ty[:, None]
    noise = rows[:, rx] * (1 - tx)[None, :] + rows[:, rx + 1] * tx[None, :]
    out: Dates = a + (b - a) * (0.1 + 0.8 * noise)
    return out


def _axis(origin: int, n: int, cell: int) -> tuple[NDArray[np.int64], Dates]:
    pos = (origin + np.arange(n) + 0.5) / cell
    i = np.floor(pos).astype(np.int64)
    return i, pos - i


def _grid(x0: int, y0: int, x1: int, y1: int, key: str) -> Dates:
    """Random values at world grid points [x0, x1) x [y0, y1), drawn in fixed blocks so any window gets the same
    ones."""
    out = np.empty((y1 - y0, x1 - x0))
    for cy in range(y0 // _CHUNK, (y1 - 1) // _CHUNK + 1):
        for cx in range(x0 // _CHUNK, (x1 - 1) // _CHUNK + 1):
            block = np.random.default_rng(stable_seed(f"dissolve:{key}:{cx},{cy}", 64)).random((_CHUNK, _CHUNK))
            gx0, gy0 = cx * _CHUNK, cy * _CHUNK
            sx0, sy0, sx1, sy1 = max(gx0, x0), max(gy0, y0), min(gx0 + _CHUNK, x1), min(gy0 + _CHUNK, y1)
            out[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = block[sy0 - gy0 : sy1 - gy0, sx0 - gx0 : sx1 - gx0]
    return out


def segment_dates(
    changed: NDArray[np.bool_],
    buildings: Dates,
    a: int,
    b: int,
    *,
    halo_px: int = HALO_PX,
    cell_px: int = DISSOLVE_CELL_PX,
    seed: int = 0,
    origin: tuple[int, int] = (0, 0),
) -> Dates:
    """The date map of one segment, as decimal years with NaN for never (see the module docstring)."""
    out = buildings.copy()
    near = halo(buildings, changed, halo_px)
    out = np.where(np.isnan(out), near, out)
    rest = changed & np.isnan(out)
    if rest.any():
        out[rest] = dissolve(changed.shape, a, b, cell_px=cell_px, seed=seed, origin=origin)[rest]
    return out
