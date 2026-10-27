from collections.abc import Mapping

import numpy as np
import pytest

from qipu_map.classes import SurfaceClass as C
from qipu_map.geo.boxes import WorldBox
from qipu_map.model import Park, Polygon, Street, StreetKind
from qipu_map.render.ground import flat_terrain, ground_shapes, rasterise_ground, roadway_width, snap_box

from .scenes import small_scene


def at(scene_kw: Mapping[str, object], x: float, y: float) -> int:
    grid = rasterise_ground(ground_shapes(small_scene(ground=scene_kw)), WorldBox(0.0, 0.0, 100.0, 100.0), 0.5)
    return int(grid.lookup(np.array([x]), np.array([y]))[0])


def test_kerbed_streets_get_a_roadway_and_sidewalks_up_to_the_lot_line() -> None:
    # 8 m right-of-way: a 4 m roadway and 2 m of sidewalk on each side
    assert at({}, 5.0, 10.0) == C.ROAD
    assert at({}, 5.0, 11.7) == C.ROAD
    assert at({}, 5.0, 13.0) == C.SIDEWALK
    assert at({}, 5.0, 15.0) == C.GROUND


def test_a_66_foot_street_has_a_ten_metre_roadway() -> None:
    assert roadway_width(StreetKind.RESIDENTIAL, 20.1) == pytest.approx(10.05)
    assert roadway_width(StreetKind.LANE, 6.0) == 6.0


def test_lanes_have_no_sidewalk_and_rails_are_rail() -> None:
    streets = (
        Street("lane", ((0.0, 10.0), (100.0, 10.0)), 6.0, StreetKind.LANE),
        Street("rail", ((0.0, 50.0), (100.0, 50.0)), 4.0, StreetKind.RAIL),
    )
    assert at({"streets": streets}, 5.0, 14.0) == C.GROUND
    assert at({"streets": streets}, 5.0, 50.0) == C.RAIL


def test_a_street_closed_before_the_year_is_gone() -> None:
    streets = (Street("s", ((0.0, 10.0), (100.0, 10.0)), 8.0, StreetKind.ARTERIAL, year_closed=2000),)
    assert at({"streets": streets}, 5.0, 10.0) == C.GROUND


def test_parks_and_water() -> None:
    assert at({}, 80.0, 80.0) == C.GRASS
    assert at({}, 10.0, 90.0) == C.WATER


def test_outside_the_area_is_none_and_holes_keep_what_was_under() -> None:
    park = Polygon(
        ((70.0, 70.0), (95.0, 70.0), (95.0, 95.0), (70.0, 95.0)),
        (((80.0, 80.0), (85.0, 80.0), (85.0, 85.0), (80.0, 85.0)),),
    )
    kw: dict[str, object] = {"parks": (Park("p", park),), "water": ()}
    assert at(kw, 75.0, 75.0) == C.GRASS
    assert at(kw, 82.0, 82.0) == C.GROUND
    grid = rasterise_ground(ground_shapes(small_scene()), WorldBox(-20.0, -20.0, 120.0, 120.0), 0.5)
    # the street runs past the box but stops at its edge; past the box there is nothing
    assert grid.lookup(np.array([-10.0, 110.0, 50.0]), np.array([10.0, 10.0, 110.0])).tolist() == [C.NONE] * 3


def test_lookup_outside_the_grid_is_none() -> None:
    grid = rasterise_ground(ground_shapes(small_scene()), WorldBox(0.0, 0.0, 10.0, 10.0), 1.0)
    assert grid.lookup(np.array([-50.0, 500.0]), np.array([5.0, 5.0])).tolist() == [C.NONE, C.NONE]


def test_snap_box_grows_to_whole_cells() -> None:
    assert snap_box(WorldBox(0.3, -0.2, 9.9, 10.1), 0.5) == (0.0, -0.5, 10.0, 10.5)


def test_flat_terrain_is_level() -> None:
    r = flat_terrain(WorldBox(0.0, 0.0, 100.0, 50.0), 3.0)
    assert r.sample([1.0, 99.0], [1.0, 49.0]).tolist() == [3.0, 3.0]
