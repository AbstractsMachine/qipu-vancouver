from dataclasses import replace

import pytest

from qipu_map.eras.rules import Basis, DatedFeature, ImprovedRule, UndatedRule
from qipu_map.eras.years import (
    apply_dated_buildings,
    apply_dated_streets,
    apply_improvements,
    centroids,
    moment,
    neighbours,
    resolve_undated,
    switch_date,
)
from qipu_map.model import StreetKind, YearSource

from .factory import building, street

RULE = UndatedRule((60.0, 120.0, 250.0), cap_year=2015, fallback_year=1950, tall_m=30.0, tall_floor_year=1960)


def test_moment_is_fixed_per_feature_and_inside_the_year() -> None:
    values = [moment(f"b{i}") for i in range(500)]
    assert all(0.1 <= v < 0.9 for v in values)
    assert moment("b1") == moment("b1")
    assert len(set(values)) > 450


def test_switch_date_boundaries() -> None:
    assert switch_date(1950, "x", 1950, 1972) is None  # in key A already
    assert switch_date(1951, "x", 1950, 1972) == pytest.approx(1951 + moment("x"))
    assert switch_date(1972, "x", 1950, 1972) == 1972.0  # in key B: held at B
    assert switch_date(1973, "x", 1950, 1972) is None
    assert switch_date(None, "x", 1950, 1972) is None


def test_undated_takes_the_median_of_the_nearest_ring() -> None:
    blds = (
        building("a", 0, 0, None),
        building("n1", 30, 0, 1910),
        building("n2", -30, 0, 1920),
        building("n3", 0, 40, 1990),
        building("far", 100, 0, 1800),
    )
    out = resolve_undated(blds, RULE)
    assert out[0].year_built == 1920
    assert out[0].year_source is YearSource.CONVENTION
    assert out[1:] == blds[1:]


def test_undated_widens_the_ring_caps_and_falls_back() -> None:
    wide = resolve_undated((building("a", 0, 0, None), building("n", 200, 0, 2020)), RULE)
    assert wide[0].year_built == 2015
    alone = resolve_undated((building("a", 0, 0, None),), RULE)
    assert alone[0].year_built == 1950


def test_resolve_leaves_a_dated_scene_alone() -> None:
    blds = (building("a", 0, 0, 1900),)
    assert resolve_undated(blds, RULE) == blds


def test_neighbours_exclude_self() -> None:
    pts = centroids((building("a", 0, 0, 1), building("b", 10, 0, 1), building("c", 100, 0, 1)))
    assert neighbours(pts, 20.0) == [[1], [0], []]
    assert centroids(()).shape == (0, 2)


def test_dated_streets_match_by_name_or_id() -> None:
    rules = (
        DatedFeature("bridge", "streets", Basis.SOURCED, "w", names=("Burrard Bridge",), opened=1932),
        DatedFeature("line", "streets", Basis.SOURCED, "t", ids=("r1",), opened=1985, closed=2001),
    )
    out = apply_dated_streets(
        (street("s1", 0, name="burrard bridge"), street("r1", 10, kind=StreetKind.RAIL), street("s3", 20)), rules
    )
    assert out[0].year_opened == 1932
    assert (out[1].year_opened, out[1].year_closed) == (1985, 2001)
    assert out[2].year_opened is None


def test_dated_buildings_correct_a_record() -> None:
    rules = (
        DatedFeature("tower", "buildings", Basis.SOURCED, "w", ids=("t",), opened=1975),
        DatedFeature("guess", "buildings", Basis.CONVENTION, "c", ids=("g",), closed=1960),
    )
    out = apply_dated_buildings((building("t", 0, 0, 1906), building("g", 50, 0, 1900), building("o", 99, 0, 1)), rules)
    assert (out[0].year_built, out[0].year_source) == (1975, YearSource.HISTORICAL)
    assert (out[1].demolished, out[1].year_source) == (1960, YearSource.CONVENTION)
    assert out[2].year_source is YearSource.TAX_ROLL


def test_an_undated_tower_never_takes_an_old_neighbourhood_year() -> None:
    blds = (building("tower", 0, 0, None, height=51.0), building("old", 30, 0, 1905))
    out = {b.id: b for b in resolve_undated(blds, RULE)}
    assert out["tower"].year_built == 1960
    assert out["tower"].year_source == YearSource.CONVENTION


def test_a_tall_building_stands_from_its_improvement_year() -> None:
    tower = replace(building("t", 0, 0, 1928, height=60.0), year_improved=1989)
    front = replace(building("f", 20, 0, 1928, height=10.0), year_improved=1989)
    out = {b.id: b for b in apply_improvements((tower, front), ImprovedRule(tall_m=30.0))}
    assert out["t"].year_built == 1989
    assert out["f"].year_built == 1928  # the low front keeps the roll's year
