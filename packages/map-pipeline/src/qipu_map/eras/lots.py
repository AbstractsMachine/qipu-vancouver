"""Cutting a big stand-in into houses.

A stand-in sits on the footprint of today's building. When that building is a tower or a block of flats, one stand-in
on its whole footprint renders as a one-storey slab the size of the tower's base, which no street of 1930 had. The lots
under such buildings were houses on narrow lots (33 by 122 ft in Vancouver), so a big footprint is cut into lots across
its long side, and each lot gets a house with side yards and a front and back setback. CONVENTION throughout: the lot
lines are drawn on today's footprint, not read from an old map.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import shapely

from qipu_map.model import Building, BuildingType, Ring, RoofForm, ccw

SIDE_YARD_M = 1.5
SETBACK_M = 3.0
HOUSE_MAX_DEPTH_M = 15.0
HOUSE_MAX_HEIGHT_M = 10.0  # two storeys and an attic
KEEP_INSIDE = 0.7  # a house must lie mostly on the old footprint
MIN_SIDE_M = 3.0


def split_into_houses(
    stand_in: Building, lot_width_m: float, lot_depth_m: float, over_m2: float
) -> tuple[Building, ...]:
    """The stand-in itself when it is small; else one house per lot cut from its footprint (`<id>-s<k>`)."""
    fp = shapely.Polygon(stand_in.footprint)
    if fp.area <= over_m2:
        return (stand_in,)
    with np.errstate(divide="ignore", invalid="ignore"):  # GEOS divides by zero on an axis-aligned box, harmlessly
        rect = shapely.minimum_rotated_rectangle(fp)
    c = [(float(x), float(y)) for x, y in shapely.get_coordinates(rect)[:4]]
    sides = [(c[1][0] - c[0][0], c[1][1] - c[0][1]), (c[3][0] - c[0][0], c[3][1] - c[0][1])]
    long_side, short_side = sorted(sides, key=lambda s: -math.hypot(*s))
    length, depth = math.hypot(*long_side), math.hypot(*short_side)
    u = (long_side[0] / length, long_side[1] / length)
    v = (short_side[0] / depth, short_side[1] / depth)
    cols, rows = max(1, round(length / lot_width_m)), max(1, round(depth / lot_depth_m))
    lot_w, lot_d = length / cols, depth / rows
    house_d = min(lot_d - 2 * SETBACK_M, HOUSE_MAX_DEPTH_M)
    houses: list[Building] = []
    for row in range(rows):
        for col in range(cols):
            a0, a1 = col * lot_w + SIDE_YARD_M, (col + 1) * lot_w - SIDE_YARD_M
            mid = (row + 0.5) * lot_d
            b0, b1 = mid - house_d / 2, mid + house_d / 2
            if a1 - a0 < MIN_SIDE_M or b1 - b0 < MIN_SIDE_M:
                continue
            ring = tuple(
                (round(c[0][0] + a * u[0] + b * v[0], 3), round(c[0][1] + a * u[1] + b * v[1], 3))
                for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))
            )
            house = shapely.Polygon(ring)
            if shapely.intersection(house, fp).area < KEEP_INSIDE * house.area:
                continue
            houses.append(_house(stand_in, ccw(ring), len(houses)))
    return tuple(houses)


def _house(stand_in: Building, ring: Ring, k: int) -> Building:
    return replace(
        stand_in,
        id=f"{stand_in.id}-s{k}",
        footprint=ring,
        height_m=min(stand_in.height_m, HOUSE_MAX_HEIGHT_M),
        kind=BuildingType.CHARACTER_HOUSE,
        roof=RoofForm.GABLE,
    )
