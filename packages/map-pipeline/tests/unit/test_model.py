import numpy as np
import pytest

from qipu_map.model import Raster, ccw, signed_area


def grid() -> Raster:
    """10 x 10 cells of 1 m, north-west corner at (0, 10), each cell holding its index."""
    return Raster(0.0, 10.0, 1.0, np.arange(100, dtype=np.float32).reshape(10, 10))


def test_sample_reads_cell_centres_and_blends_between_them() -> None:
    r = grid()
    assert r.value_at(0.5, 9.5) == 0.0
    assert r.value_at(1.0, 9.5) == pytest.approx(0.5)
    assert r.value_at(0.5, 9.0) == pytest.approx(5.0)


def test_sample_clamps_to_the_edge() -> None:
    r = grid()
    assert r.sample([-50.0, 500.0], [50.0, -50.0]).tolist() == [0.0, 99.0]


def test_sample_over_arrays_matches_one_point_at_a_time() -> None:
    r = grid()
    xs, ys = np.array([0.2, 3.7, 9.9, 5.0]), np.array([0.1, 4.4, 9.9, 5.5])
    assert r.sample(xs, ys).tolist() == [r.value_at(x, y) for x, y in zip(xs, ys, strict=True)]
    assert r.sample(xs.reshape(2, 2), ys.reshape(2, 2)).shape == (2, 2)


def test_crop_keeps_the_cells_that_touch_the_box() -> None:
    c = grid().crop((2.5, 3.5, 4.5, 6.5))
    assert (c.x0, c.y0, c.cell) == (2.0, 7.0, 1.0)
    assert c.data.tolist() == [[32, 33, 34], [42, 43, 44], [52, 53, 54], [62, 63, 64]]


def test_crop_grows_the_box_by_the_margin() -> None:
    r = grid()
    c = r.crop((3.0, 3.0, 5.0, 6.0), margin=1.0)
    assert (c.x0, c.y0, c.data.shape) == (2.0, 7.0, (5, 4))
    assert c.data[0, 0] == r.data[3, 2]


def test_crop_outside_the_grid_keeps_one_edge_cell() -> None:
    c = grid().crop((50.0, 50.0, 60.0, 60.0))
    assert c.data.shape == (1, 1)
    assert c.data[0, 0] == 9.0


def test_ccw_turns_a_clockwise_ring_round() -> None:
    square = ((0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0))
    assert signed_area(square) == -4.0
    assert ccw(square) == tuple(reversed(square))
    assert ccw(ccw(square)) == ccw(square)
