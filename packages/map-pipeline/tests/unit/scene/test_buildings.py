from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
import shapely

from qipu_map.model import BuildingType, RoofForm, YearSource
from qipu_map.scene.buildings import Footprint, beside_bigger, build, build_all, clean, is_sliver
from qipu_map.scene.podium import tower_outline
from tests.unit.scene import synth


def fp(fid: str, outline: shapely.Polygon, **kw: Any) -> Footprint:
    base = Footprint(
        fid,
        outline,
        year_built=1912,
        year_source="tax_roll",
        year_improved=None,
        height_m=None,
        levels=None,
        use="RT-7",
    )
    return replace(base, **kw)


def test_sliver_rule() -> None:
    """A 7 m² footprint read at 35 m stood as a chimney in a park on the live map."""
    assert is_sliver(7.0, 35.0)
    assert not is_sliver(7.0, 3.0)
    assert not is_sliver(400.0, 35.0)


def test_clean_keeps_the_largest_part_without_holes_counter_clockwise() -> None:
    donut = shapely.Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(4, 4), (4, 6), (6, 6), (6, 4)]])
    parts = shapely.MultiPolygon([donut, shapely.box(20, 20, 21, 21)])
    out = clean(parts)
    assert out is not None
    assert out.area == 100.0
    assert not out.interiors
    assert out.exterior.is_ccw
    assert clean(shapely.box(0, 0, 1, 1)) is None
    bowtie = shapely.Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert clean(bowtie) is not None


def test_beside_bigger() -> None:
    house, garage, far = shapely.box(0, 0, 10, 15), shapely.box(0, 25, 6, 31), shapely.box(200, 0, 206, 6)
    assert beside_bigger([house, garage, far]) == [False, True, False]


def test_build_a_measured_gabled_house() -> None:
    b = build(fp("h", shapely.box(*synth.HOUSE)), synth.gable(), synth.grid(), near_bigger=False)
    assert b is not None
    assert b.building.roof is RoofForm.GABLE
    assert b.roof_source == "lidar"
    assert b.building.kind is BuildingType.CHARACTER_HOUSE
    assert b.height_source == "lidar"
    assert 9.0 < b.building.height_m < 11.0  # the ridge: 6 m eaves + 0.9 x 5 m
    assert b.building.ground_m == synth.GROUND_M
    assert b.building.year_source is YearSource.TAX_ROLL


def test_unmeasured_building_takes_its_type_default() -> None:
    out = build(
        fp("x", shapely.box(100, 100, 110, 116), year_source=None, year_built=None), synth.flat(), synth.grid(), False
    )
    assert out is not None
    assert out.height_source == "default"
    assert out.roof_source == "type"
    assert out.building.year_source is YearSource.CONVENTION


def test_build_all_drops_slivers_and_sorts() -> None:
    slim = shapely.box(30, 30, 33, 32)  # 6 m², read at 10 m: over 3x its side
    dsm = synth.with_roof((30.0, 30.0, 33.0, 32.0), lambda x, _y: x * 0 + 10.0)
    buildings, notes = build_all([fp("b", shapely.box(*synth.HOUSE)), fp("a", slim, height_m=10.0)], dsm, synth.grid())
    assert [b.id for b in buildings] == ["b"]
    assert notes["dropped"] == {"sliver": 1}


def test_conventional_roofs_are_stable() -> None:
    one = build(fp("x", shapely.box(100, 100, 110, 116)), synth.flat(), synth.grid(), False)
    two = build(fp("x", shapely.box(100, 100, 110, 116)), synth.flat(), synth.grid(), False)
    assert one == two


def test_a_tower_on_its_podium_is_split_in_two() -> None:
    """One outline, a 30 x 30 m podium of 8 m with a 10 x 10 m tower of 50 m on it."""
    dsm = synth.with_roof(
        (5.0, 5.0, 35.0, 35.0), lambda x, y: np.where((x > 10) & (x < 20) & (y > 10) & (y < 20), 50.0, 8.0)
    )
    built = build(fp("p", shapely.box(5, 5, 35, 35), use="C-2", year_built=1972), dsm, synth.grid(), False)
    assert built is not None
    assert built.rule == "tower on a podium"
    assert built.building.kind is BuildingType.PODIUM_TOWER
    assert built.building.height_m == 8.0
    assert built.tower is not None
    assert built.tower.id == "p-tower"
    assert built.tower.kind is BuildingType.POINT_TOWER
    assert built.tower.height_m == 50.0
    assert shapely.Polygon(built.tower.footprint).area == pytest.approx(100.0, rel=0.25)
    buildings, _ = build_all([fp("p", shapely.box(5, 5, 35, 35), use="C-2")], dsm, synth.grid())
    assert [b.id for b in buildings] == ["p", "p-tower"]


def test_no_tower_found_keeps_the_podium_alone() -> None:
    assert tower_outline(shapely.box(5, 5, 35, 35), synth.flat(), synth.grid(), 8.0, 50.0) is None
    assert tower_outline(shapely.box(100, 100, 110, 110), synth.flat(), synth.grid(), 8.0, 50.0) is None
