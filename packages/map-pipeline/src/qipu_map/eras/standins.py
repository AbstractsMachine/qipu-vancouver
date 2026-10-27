"""Stand-ins: period houses on lots whose old building is in no record.

The tax roll describes the buildings standing today. A lot where a 1975 tower replaced three 1905 houses shows nothing
in 1950 unless something stands in for the lost houses. Without stand-ins the West End of 1950 had about 12 % of its
ground built, where the 1950 air photos show 50 to 90 %.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import shapely
from numpy.typing import NDArray

from qipu_map.eras.lots import split_into_houses
from qipu_map.eras.rules import Evidence, StandInRule
from qipu_map.eras.years import centroids, footprints, neighbours
from qipu_map.model import Building, BuildingType, Raster, RoofForm, YearSource
from qipu_map.values import most_common

STANDIN_SUFFIX = "~standin"


def evidence_level(evidence: tuple[Evidence, Raster] | None, x: float, y: float) -> float:
    """How built up the period's mask says a point was, 0 to 1 (0 when no mask speaks for the year)."""
    if evidence is None:
        return 0.0
    ev, raster = evidence
    v = raster.value_at(x, y)
    return min(1.0, max(0.0, (v - ev.low) / (ev.high - ev.low)))


def stand_ins(
    buildings: Sequence[Building], year: int, rule: StandInRule, evidence: tuple[Evidence, Raster] | None = None
) -> tuple[Building, ...]:
    """The stand-ins for `year`, in the order of `buildings`: one per lot that qualifies (see `rules.StandInRule`), or a
    row of houses where the lot is big.

    `buildings` are today's, with their years resolved. A stand-in never covers more than `max_overlap` of its footprint
    with a building that stands in `year`: a convention does not draw over a record.
    """
    pts = centroids(buildings)
    near = neighbours(pts, rule.radius_m)
    standing = [b.stands_in(year) for b in buildings]
    standing_fp = footprints([b for b, s in zip(buildings, standing, strict=True) if s])
    tree = shapely.STRtree(standing_fp)
    out: list[Building] = []
    for i, b in enumerate(buildings):
        if standing[i] or b.year_built is None or b.year_built <= year:
            continue
        old = [buildings[j] for j in near[i] if standing[j]]
        says = evidence is not None and evidence_level(evidence, *pts[i]) > rule.evidence_threshold
        says = says and evidence is not None and b.year_built > evidence[0].photo_year + rule.evidence_margin_years
        if not says and (len(near[i]) < rule.min_neighbours or len(old) / len(near[i]) < rule.old_share):
            continue
        period = int(np.median([n.year_built or 0 for n in old])) if old else rule.fallback_year
        if b.year_built - period < rule.gap_years and not says:
            continue
        if _overlap(b, tree, standing_fp) > rule.max_overlap:
            continue
        stand_in = _stand_in(b, old, period, year, rule)
        out.extend(split_into_houses(stand_in, rule.lot_width_m, rule.lot_depth_m, rule.split_over_m2))
    return tuple(out)


def _overlap(b: Building, tree: shapely.STRtree, standing_fp: NDArray[np.object_]) -> float:
    fp = shapely.Polygon(b.footprint)
    if fp.area <= 0:
        return 1.0
    hits = tree.query(fp, predicate="intersects")
    return max((float(shapely.intersection(fp, standing_fp[j]).area) / fp.area for j in hits), default=0.0)


def _stand_in(b: Building, old: list[Building], period: int, year: int, rule: StandInRule) -> Building:
    height = float(np.median([n.height_m for n in old])) if old else rule.default_height_m
    if year < rule.early_year:
        height = min(height, rule.early_max_height_m)
    kind = most_common([n.kind for n in old]) or BuildingType.CHARACTER_HOUSE
    roof = most_common([n.roof for n in old]) or RoofForm.GABLE
    return Building(
        id=b.id + STANDIN_SUFFIX,
        footprint=b.footprint,
        ground_m=b.ground_m,
        height_m=height,
        roof=roof,
        kind=kind,
        year_built=min(period, year),
        year_source=YearSource.CONVENTION,
        demolished=b.year_built,
    )
