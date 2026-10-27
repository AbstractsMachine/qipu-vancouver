"""The scene of a past year, derived from today's.

Nothing is drawn here; the result is a `model.Scene` the renderer draws exactly like today's. What changes from today:
buildings not yet built or already demolished are left out, stand-ins fill lots that were built up before today's
building, streets and trees follow their dates, and area overrides apply their period rules.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import replace

import shapely
from shapely.geometry.base import BaseGeometry

from qipu_map.eras.rules import AreaOverride, EraRules, Evidence
from qipu_map.eras.standins import stand_ins
from qipu_map.eras.years import (
    apply_dated_buildings,
    apply_dated_streets,
    apply_improvements,
    footprints,
    resolve_undated,
)
from qipu_map.geo.projection import LocalProjection
from qipu_map.model import Building, Park, Polygon, Raster, Scene, Street, StreetKind, Tree, YearSource


def prepare_today(today: Scene, rules: EraRules) -> Scene:
    """Today's scene with every year the eras need: dated streets, corrected records, undated buildings resolved.

    Run once; both the past scenes and the date maps read the years from this scene.
    """
    dated = apply_improvements(apply_dated_buildings(today.buildings, rules.dated), rules.improved)
    buildings = resolve_undated(dated, rules.undated)
    return replace(today, buildings=buildings, streets=apply_dated_streets(today.streets, rules.dated))


def derive_past_scene(
    today: Scene,
    year: int,
    rules: EraRules,
    projection: LocalProjection,
    evidence: tuple[Evidence, Raster] | None = None,
) -> Scene:
    """The scene of `year`. `today` must come from `prepare_today`."""
    if year >= today.year:
        raise ValueError(f"{year} is not before today's scene ({today.year})")
    areas = [(a, _area_shape(a, projection)) for a in rules.areas if a.holds(year)]
    counts: Counter[str] = Counter()

    buildings = []
    for b in today.buildings:
        if not b.stands_in(year):
            counts["not standing yet or demolished (sourced)"] += 1
            continue
        if _in_water(b, areas) and b.year_source is YearSource.CONVENTION:
            counts["under water then (area override)"] += 1
            continue
        if _in_water(b, areas):
            counts["kept: a record says it stood on land the area override calls water"] += 1
        buildings.append(b)
    extra = [s for s in stand_ins(today.buildings, year, rules.standins, evidence) if not _in_water(s, areas)]
    counts["stand-ins (convention)"] = len(extra)
    buildings.extend(extra)

    streets = _streets(today.streets, year, rules, areas, buildings)
    counts["streets left out"] = len(today.streets) - len(streets)
    trees = tuple(t for t in today.trees if _tree_stands(t, year, areas))
    counts["trees left out"] = len(today.trees) - len(trees)
    parks = tuple(p for p in today.parks if not _hits(_park_point(p), areas, lambda a: a.water or a.drop_parks))
    counts["parks left out"] = len(today.parks) - len(parks)
    water = today.water + tuple(_local_polygon(a, projection) for a, _ in areas if a.water)

    return replace(
        today,
        year=year,
        buildings=tuple(buildings),
        streets=streets,
        trees=trees,
        parks=parks,
        water=water,
        notes={**today.notes, "eras": {"derived_from": today.year, "counts": dict(sorted(counts.items()))}},
    )


Areas = list[tuple[AreaOverride, BaseGeometry]]


def _area_shape(a: AreaOverride, projection: LocalProjection) -> BaseGeometry:
    return shapely.Polygon([projection.to_world(lon, lat) for lon, lat in a.polygon])


def _local_polygon(a: AreaOverride, projection: LocalProjection) -> Polygon:
    return Polygon(tuple(projection.to_world(lon, lat) for lon, lat in a.polygon))


def _hits(point: BaseGeometry, areas: Areas, effect: Callable[[AreaOverride], bool]) -> bool:
    return any(effect(a) and shape.contains(point) for a, shape in areas)


def _in_water(b: Building, areas: Areas) -> bool:
    return _hits(shapely.Polygon(b.footprint).representative_point(), areas, lambda a: a.water)


def _park_point(p: Park) -> BaseGeometry:
    return shapely.Polygon(p.shape.outer).representative_point()


def _tree_stands(t: Tree, year: int, areas: Areas) -> bool:
    if t.year_planted is not None and t.year_planted > year:
        return False
    return not _hits(shapely.Point(t.x, t.y), areas, lambda a: a.water or a.drop_trees)


def _street_dated_in(s: Street, year: int, rules: EraRules) -> bool:
    if s.year_closed is not None and s.year_closed <= year:
        return False
    if s.year_opened is None:
        return s.kind is not StreetKind.RAIL or rules.undated_rail_in_past
    return s.year_opened <= year


def _streets(
    streets: tuple[Street, ...], year: int, rules: EraRules, areas: Areas, buildings: list[Building]
) -> tuple[Street, ...]:
    frontage = [(a, shape) for a, shape in areas if a.street_frontage_m > 0]
    tree = shapely.STRtree(footprints(buildings)) if frontage else None
    out = []
    for s in streets:
        if not _street_dated_in(s, year, rules):
            continue
        mid = shapely.LineString(s.line).interpolate(0.5, normalized=True)
        if _hits(mid, areas, lambda a: a.water):
            continue
        inside = [a for a, shape in frontage if shape.contains(mid)]
        if inside and tree is not None:
            reach = max(a.street_frontage_m for a in inside)
            if not len(tree.query(shapely.LineString(s.line), predicate="dwithin", distance=reach)):
                continue
        out.append(s)
    return tuple(out)
