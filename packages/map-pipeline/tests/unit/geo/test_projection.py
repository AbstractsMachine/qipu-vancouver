import numpy as np
import pytest

from qipu_map.geo.boxes import GeoBox
from qipu_map.geo.projection import LocalProjection

PROJ = LocalProjection(lon0=-123.1302, lat0=49.2565)


def test_origin_is_zero() -> None:
    assert PROJ.to_world(-123.1302, 49.2565) == (0.0, 0.0)


def test_round_trip() -> None:
    x, y = PROJ.to_world(-123.14, 49.285)
    assert PROJ.to_lonlat(x, y) == pytest.approx((-123.14, 49.285))


def test_a_degree_of_latitude_is_the_engine_constant() -> None:
    _, y = PROJ.to_world(-123.1302, 50.2565)
    assert y == pytest.approx(111_320.0)


def test_box_to_world_orders_corners() -> None:
    x0, y0, x1, y1 = PROJ.box_to_world(GeoBox(49.284, -123.143, 49.2878, -123.137))
    assert x0 < x1
    assert y0 < y1
    assert 400 < x1 - x0 < 500


def test_arrays_project_like_points() -> None:
    lon, lat = np.array([-123.14, -123.12]), np.array([49.285, 49.25])
    xs, ys = PROJ.to_world(lon, lat)
    assert [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)] == [
        PROJ.to_world(-123.14, 49.285),
        PROJ.to_world(-123.12, 49.25),
    ]
    back_lon, back_lat = PROJ.to_lonlat(xs, ys)
    assert back_lon == pytest.approx(lon)
    assert back_lat == pytest.approx(lat)
