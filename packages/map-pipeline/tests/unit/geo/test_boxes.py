import json

import pytest

from qipu_map.geo.boxes import GeoBox, WorldBox
from qipu_map.geo.projection import LocalProjection

PROJ = LocalProjection(lon0=-123.1302, lat0=49.2565)


def test_a_geo_box_grows_by_metres_on_every_side() -> None:
    box = GeoBox(49.28, -123.14, 49.29, -123.13)
    grown = box.grown(100.0, PROJ)
    x0, y0, x1, y1 = PROJ.box_to_world(box)
    gx0, gy0, gx1, gy1 = PROJ.box_to_world(grown)
    assert (x0 - gx0, y0 - gy0, gx1 - x1, gy1 - y1) == pytest.approx((100.0, 100.0, 100.0, 100.0))


def test_a_geo_box_in_the_formats_the_sources_take() -> None:
    box = GeoBox(1.0, 2.0, 3.0, 4.0)
    assert box.overpass() == "(1.0,2.0,3.0,4.0)"
    assert box.wkt() == "POLYGON((2.0 1.0, 4.0 1.0, 4.0 3.0, 2.0 3.0, 2.0 1.0))"
    assert box.shape().bounds == (2.0, 1.0, 4.0, 3.0)


def test_a_world_box_grows_intersects_and_stays_four_numbers() -> None:
    a = WorldBox(0.0, 0.0, 10.0, 10.0)
    assert a.grown(1.0) == (-1.0, -1.0, 11.0, 11.0)
    assert a.intersects(WorldBox(10.0, 5.0, 20.0, 6.0))
    assert not a.intersects(WorldBox(10.1, 0.0, 20.0, 1.0))
    assert a.shape().area == 100.0
    assert json.loads(json.dumps(a)) == [0.0, 0.0, 10.0, 10.0]
