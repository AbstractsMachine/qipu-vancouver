from __future__ import annotations

import shapely

from qipu_map.ingest.normalise import nature, water
from tests.unit.ingest.helpers import fc, line, pt, sq, way

BOX = sq(0, 0, 20, 20)


def test_sea_side_is_right_of_the_coastline() -> None:
    coast = [line((0, 10), (20, 10))]  # running east: land north (left), sea south (right)
    assert water.sea_side(pt(5, 2), coast)
    assert not water.sea_side(pt(5, 18), coast)
    assert not water.sea_side(pt(5, 2), [])


def test_sea_side_at_a_sharp_right_turn_is_the_wedge() -> None:
    # East, then back west and a little south: the sea is the thin wedge between the two segments. A point past the
    # corner is right of the first segment but left of the second, and it is land.
    coast = [line((0, 0), (10, 0), (0, -1))]
    assert not water.sea_side(pt(11, -0.05), coast)
    assert water.sea_side(pt(5, -0.2), coast)


def test_sea_side_at_a_left_turn_where_two_ways_meet() -> None:
    # Two OSM ways meeting at (10, 0), turning sharply back west and a little north: the sea is everything outside.
    coast = [line((10, 0), (0, 0.5)), line((0, 0), (10, 0))]  # listed in the other order
    assert water.sea_side(pt(11, 0.05), coast)
    assert not water.sea_side(pt(5, 0.1), coast)


def test_sea_is_cut_along_the_city_shoreline_and_sided_by_osm() -> None:
    shore = [line((-1, 8), (21, 8))]  # the City's line, a little south of OSM's
    coast = [line((-5, 10), (25, 10))]
    seas = water.sea(BOX, shore, coast)
    assert len(seas) == 1
    assert seas[0].symmetric_difference(sq(0, 0, 20, 8)).area < 1e-14


def test_osm_coastline_cuts_when_the_city_has_no_shoreline_here() -> None:
    seas = water.sea(BOX, [], [line((-5, 10), (25, 10))])
    assert abs(seas[0].area - sq(0, 0, 20, 10).area) < 1e-12


def test_no_coastline_no_sea() -> None:
    assert water.sea(BOX, [line((-1, 8), (21, 8))], []) == []


def test_water_layer_kinds() -> None:
    osm = {
        "elements": [
            way(1, line((-5, 10), (25, 10)), natural="coastline"),
            way(2, sq(2, 12, 2, 2), natural="water", water="pond"),
            way(3, sq(6, 12, 2, 2), natural="water", water="lake"),
            way(4, sq(10, 12, 2, 2), waterway="riverbank"),
            way(5, sq(30, 30, 2, 2), natural="water"),  # outside the box
            way(6, sq(14, 12, 2, 2), natural="wood"),
        ]
    }
    feats = water.water(fc(), osm, BOX)
    assert sorted((f.id, f.props["kind"]) for f in feats) == [
        ("osm-w2", "pond"),
        ("osm-w3", "lake"),
        ("osm-w4", "river"),
        ("sea", "sea"),
    ]


def test_trees() -> None:
    raw = fc(
        (pt(1, 1), {"asset_id": 7, "genus_name": "ACER", "species_name": "RUBRUM", "height_m": 9.5, "diameter_cm": 0}),
        (pt(2, 2), {"asset_id": 8, "genus_name": " ", "date_planted": "1999-04-01"}),
        (sq(0, 0), {"asset_id": 9}),
    )
    got = {f.id: f.props for f in nature.trees(raw)}
    assert got == {
        "tree-7": {"genus": "ACER", "species": "RUBRUM", "height_m": 9.5, "diameter_cm": None, "year_planted": None},
        "tree-8": {"genus": None, "species": None, "height_m": None, "diameter_cm": None, "year_planted": 1999},
    }


def test_parks_are_cut_to_the_box_and_split() -> None:
    # a U-shaped park whose arms leave the box separately once the bottom is cut away
    u = shapely.union_all([sq(2, -10, 2, 25), sq(10, -10, 2, 25), sq(2, -10, 10, 5)])
    raw = fc((u, {"object_id": 3, "park_name": "Nelson Park"}), (sq(50, 50), {"object_id": 4, "park_name": "Far"}))
    got = nature.parks(raw, BOX)
    assert sorted(f.id for f in got) == ["park-3#0", "park-3#1"]
    assert all(f.props["name"] == "Nelson Park" and BOX.covers(f.geometry) for f in got)
