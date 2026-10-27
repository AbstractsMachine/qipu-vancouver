from __future__ import annotations

import pytest
import shapely

from qipu_map.geo.boxes import WorldBox
from qipu_map.model import Polygon, StreetKind
from qipu_map.scene.ground import DEFAULT_WIDTH_M, clip_lines, parks, street, to_polygons, water_and_land

BOX = WorldBox(0.0, 0.0, 100.0, 100.0)


def area(polys: tuple[Polygon, ...]) -> float:
    return float(sum(shapely.Polygon(p.outer, p.holes).area for p in polys))


def test_street_width_defaults_by_kind() -> None:
    assert street("s", [(0, 0), (10, 0)], "lane", None, None).width_m == DEFAULT_WIDTH_M[StreetKind.LANE]
    assert street("s", [(0, 0), (10, 0)], "arterial", 22.5, "Davie St").width_m == 22.5


def test_streets_are_clipped_to_the_box_with_a_margin() -> None:
    s = street("s", [(-50.0, 50.0), (150.0, 50.0)], "residential", None, None)
    (cut,) = clip_lines([s], BOX)
    assert cut.line[0][0] == pytest.approx(-9.0)
    assert cut.line[-1][0] == pytest.approx(109.0)
    assert clip_lines([street("far", [(500, 500), (600, 500)], "lane", None, None)], BOX) == []


def test_a_street_leaving_and_coming_back_becomes_two_pieces() -> None:
    s = street("s", [(10.0, 50.0), (10.0, 200.0), (90.0, 200.0), (90.0, 50.0)], "lane", None, None)
    assert [c.id for c in clip_lines([s], BOX)] == ["s", "s-1"]


def test_land_is_the_box_minus_the_water() -> None:
    sea = shapely.box(-50, -50, 150, 30)
    water, land = water_and_land([sea], BOX)
    assert area(water) == pytest.approx(3000.0)
    assert area(land) == pytest.approx(7000.0)


def test_no_water_means_all_land() -> None:
    water, land = water_and_land([], BOX)
    assert water == ()
    assert area(land) == pytest.approx(10_000.0)


def test_a_lake_is_a_hole_in_the_land() -> None:
    _water, land = water_and_land([shapely.box(40, 40, 60, 60)], BOX)
    (only,) = land
    assert len(only.holes) == 1
    assert shapely.LinearRing(only.outer).is_ccw
    assert not shapely.LinearRing(only.holes[0]).is_ccw


def test_parks_are_clipped_and_split() -> None:
    two_sides = shapely.MultiPolygon([shapely.box(-10, 0, 10, 10), shapely.box(90, 0, 110, 10)])
    out = parks([("p", two_sides, "Nelson Park")], BOX)
    assert [p.id for p in out] == ["p", "p-1"]
    assert area(tuple(p.shape for p in out)) == pytest.approx(200.0)


def test_crumbs_are_dropped() -> None:
    assert to_polygons(shapely.box(0, 0, 0.5, 0.5)) == ()
