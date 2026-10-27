"""Tiny scenes for the eras tests: square buildings on a grid, a street, a tree, a park."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from qipu_map.eras.rules import EraRules, ImprovedRule, StandInRule, UndatedRule
from qipu_map.geo.boxes import WorldBox
from qipu_map.model import (
    Building,
    BuildingType,
    Park,
    Polygon,
    RoofForm,
    Scene,
    Street,
    StreetKind,
    Tree,
    TreeForm,
    YearSource,
)


def square(x: float, y: float, side: float = 10.0) -> tuple[tuple[float, float], ...]:
    h = side / 2
    return ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h))


def building(
    id: str,
    x: float,
    y: float,
    year: int | None,
    *,
    source: YearSource = YearSource.TAX_ROLL,
    demolished: int | None = None,
    height: float = 9.0,
    kind: BuildingType = BuildingType.CHARACTER_HOUSE,
    side: float = 10.0,
) -> Building:
    return Building(
        id=id,
        footprint=square(x, y, side),
        ground_m=0.0,
        height_m=height,
        roof=RoofForm.GABLE,
        kind=kind,
        year_built=year,
        year_source=source if year is not None else YearSource.CONVENTION,
        demolished=demolished,
    )


def scene(
    buildings: tuple[Building, ...] = (),
    streets: tuple[Street, ...] = (),
    trees: tuple[Tree, ...] = (),
    parks: tuple[Park, ...] = (),
    year: int = 2026,
) -> Scene:
    return Scene(
        city="ca/test",
        area="block",
        year=year,
        box=WorldBox(-200.0, -200.0, 200.0, 200.0),
        buildings=buildings,
        streets=streets,
        trees=trees,
        parks=parks,
        water=(),
        land=(),
        terrain_file="terrain.npz",
    )


def street(
    id: str, y: float, *, name: str | None = None, kind: StreetKind = StreetKind.RESIDENTIAL, **kw: int
) -> Street:
    return Street(id=id, line=((-100.0, y), (100.0, y)), width_m=10.0, kind=kind, name=name, **kw)


def tree(id: str, x: float, y: float, planted: int | None = None) -> Tree:
    return Tree(id=id, x=x, y=y, height_m=10.0, crown_m=6.0, form=TreeForm.BROADLEAF, year_planted=planted)


def park(id: str, x: float, y: float) -> Park:
    return Park(id=id, shape=Polygon(square(x, y, 30.0)), name=id)


STANDINS = StandInRule(
    radius_m=80.0,
    min_neighbours=6,
    old_share=0.6,
    gap_years=25,
    fallback_year=1910,
    default_height_m=9.0,
    early_year=1930,
    early_max_height_m=14.0,
    evidence_threshold=0.3,
    evidence_margin_years=5,
    max_overlap=0.3,
)


def rules(**kw: Any) -> EraRules:
    """Small rules for the tests; keyword arguments replace fields."""
    base = EraRules(
        city="ca/test",
        improved=ImprovedRule(tall_m=30.0),
        undated=UndatedRule((60.0, 120.0, 250.0), cap_year=2015, fallback_year=1950, tall_m=30.0, tall_floor_year=1960),
        standins=STANDINS,
        undated_rail_in_past=False,
        evidence=(),
        dated=(),
        areas=(),
    )
    return replace(base, **kw)


def old_street(year: int = 1905, n: int = 8) -> tuple[Building, ...]:
    """A row of `n` houses of `year` along y = 0, 20 m apart, starting at x = -70."""
    return tuple(building(f"h{i}", -70.0 + 20.0 * i, 0.0, year) for i in range(n))
