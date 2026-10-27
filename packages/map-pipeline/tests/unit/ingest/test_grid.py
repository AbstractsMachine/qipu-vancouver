from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from qipu_map.geo.boxes import WorldBox
from qipu_map.ingest import grid as g


def test_covering_snaps_outward_to_whole_cells() -> None:
    lg = g.LocalGrid.covering(WorldBox(10.4, -5.2, 20.6, 3.1), margin_m=2.0)
    assert (lg.x0, lg.y0, lg.w, lg.h) == (8.0, 6.0, 15, 14)  # x 8..23, y -8..6


def test_centres_run_east_then_south() -> None:
    xx, yy = g.LocalGrid(0.0, 10.0, 2.0, 3, 2).centres()
    assert xx.tolist() == [[1.0, 3.0, 5.0], [1.0, 3.0, 5.0]]
    assert yy.tolist() == [[9.0, 9.0, 9.0], [7.0, 7.0, 7.0]]


def test_sample_nearest_reads_the_cell_a_point_falls_in() -> None:
    data = np.arange(12, dtype=np.float32).reshape(3, 4)
    data[2, 3] = -9999.0
    t = (1.0, 0.0, 100.0, 0.0, -1.0, 50.0)  # 1 m cells, north-west corner at (100, 50)
    ex = np.array([100.5, 103.9, 101.0, 103.5, 99.9, 100.5])
    ny = np.array([49.5, 49.9, 48.0, 47.5, 49.5, 46.9])
    got = g.sample_nearest(data, t, -9999.0, ex, ny)
    assert got[:3].tolist() == [0.0, 3.0, 9.0]
    assert np.isnan(got[3:]).all()  # nodata, west of the raster, south of it


def test_sample_nearest_refuses_rotated_rasters() -> None:
    with pytest.raises(ValueError, match="rotated"):
        g.sample_nearest(np.zeros((1, 1), np.float32), (1.0, 0.1, 0.0, 0.0, -1.0, 0.0), None, np.zeros(1), np.zeros(1))


def test_first_tile_wins_where_two_overlap() -> None:
    a = np.array([1.0, np.nan, np.nan], np.float32)
    b = np.array([5.0, 6.0, np.nan], np.float32)
    assert np.array_equal(g.fill_missing(a, b), np.array([1.0, 6.0, np.nan], np.float32), equal_nan=True)


def test_decimetres_round_trip_keeps_nan_and_clips() -> None:
    v = np.array([[12.34, -0.05, np.nan, 5000.0]], np.float32)
    dm = g.to_decimetres(v)
    assert dm.dtype == np.int16
    back = g.from_decimetres(dm)
    assert back[0, 0] == pytest.approx(12.3)
    assert back[0, 1] == pytest.approx(-0.1) or back[0, 1] == pytest.approx(0.0)
    assert np.isnan(back[0, 2])
    assert back[0, 3] == pytest.approx(3276.7)


def test_grid_file_round_trip(tmp_path: Path) -> None:
    lg = g.LocalGrid(5.0, 9.0, 1.0, 2, 2)
    p = tmp_path / "x.npz"
    p.write_bytes(g.grid_bytes(lg, np.array([[1.0, 2.5], [np.nan, -3.0]], np.float32)))
    r = g.load_grid(p)
    assert (r.x0, r.y0, r.cell) == (5.0, 9.0, 1.0)
    assert np.array_equal(r.data, np.array([[1.0, 2.5], [np.nan, -3.0]], np.float32), equal_nan=True)
