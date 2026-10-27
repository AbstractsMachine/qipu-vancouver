import numpy as np
import pytest

from qipu_map.eras.datemap import (
    building_pixels,
    dissolve,
    halo,
    segment_building_dates,
    segment_dates,
)
from qipu_map.eras.years import moment

from .factory import building


def test_building_dates_per_scene() -> None:
    old = building("old", 0, 0, 1900, demolished=1960)
    keep = building("keep", 20, 0, 1900)
    new = building("new", 40, 0, 1955)
    removed = building("removed", 60, 0, 1900)  # gone from B without a record date: left to the dissolve
    da, db = segment_building_dates((old, keep, removed), (keep, new), 1950, 1972)
    assert np.isnan(da[0])
    assert np.isnan(db[0])
    assert da[1] == pytest.approx(1960 + moment("old"))
    assert np.isnan(da[2])
    assert np.isnan(da[3])
    assert np.isnan(db[1])
    assert db[2] == pytest.approx(1955 + moment("new"))


def _synthetic() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A 40 x 60 canvas: building 1 of scene A at columns 5-9 (goes in 1960), building 2 of B at 40-44 (new in 1965)."""
    ids_a = np.zeros((40, 60), np.int64)
    ids_b = np.zeros((40, 60), np.int64)
    ids_a[10:20, 5:10] = 1
    ids_b[10:20, 40:45] = 2
    da = np.array([np.nan, 1960.3])
    db = np.array([np.nan, np.nan, 1965.6])
    return ids_a, ids_b, da, db


def test_buildings_are_dated_from_the_id_pass() -> None:
    ids_a, ids_b, da, db = _synthetic()
    px = building_pixels(ids_a, ids_b, da, db)
    assert (px[10:20, 5:10] == 1960.3).all()
    assert (px[10:20, 40:45] == 1965.6).all()
    assert np.isnan(px[0, 0])
    assert np.isnan(px[30:, :]).all()
    both = building_pixels(ids_a, ids_a, da, np.array([np.nan, 1955.0]))
    assert (both[10:20, 5:10] == 1955.0).all()  # the earliest of the two wins


def test_an_id_the_scene_lacks_is_an_error() -> None:
    with pytest.raises(ValueError, match="rendered from this scene"):
        building_pixels(np.array([[5]]), np.array([[0]]), np.array([np.nan]), np.array([np.nan]))


def test_halo_reaches_12_px_and_only_changed_pixels() -> None:
    dates = np.full((1, 40), np.nan)
    dates[0, 0] = 1960.0
    out = halo(dates, np.ones((1, 40), bool))
    assert (out[0, 1:13] == 1960.0).all()
    assert np.isnan(out[0, 13:]).all()
    assert np.isnan(out[0, 0])
    some = np.zeros((1, 40), bool)
    some[0, 5] = True
    assert np.flatnonzero(~np.isnan(halo(dates, some))).tolist() == [5]


def test_halo_takes_the_nearest_building() -> None:
    dates = np.full((1, 21), np.nan)
    dates[0, 0], dates[0, 20] = 1955.0, 1965.0
    out = halo(dates, np.ones((1, 21), bool))
    assert out[0, 3] == 1955.0
    assert out[0, 17] == 1965.0


def test_dissolve_is_deterministic_and_within_the_segment() -> None:
    a = dissolve((300, 400), 1950, 1972, cell_px=64, seed=3)
    assert np.array_equal(a, dissolve((300, 400), 1950, 1972, cell_px=64, seed=3))
    assert not np.array_equal(a, dissolve((300, 400), 1972, 1982, cell_px=64, seed=3))
    lo, hi = float(np.min(a)), float(np.max(a))
    assert lo >= 1950 + 0.1 * 22 - 1e-9
    assert hi <= 1950 + 0.9 * 22 + 1e-9
    assert hi - lo > 5  # it does spread over the segment


def test_dissolve_is_fixed_to_world_pixels() -> None:
    whole = dissolve((300, 400), 1950, 1972, cell_px=64, seed=3, origin=(-1000, 500))
    part = dissolve((100, 150), 1950, 1972, cell_px=64, seed=3, origin=(-1000 + 170, 500 + 90))
    assert np.allclose(part, whole[90:190, 170:320])


def test_dissolve_is_smooth_with_no_block_edges() -> None:
    cell = 32
    a = dissolve((256, 256), 1950, 1972, cell_px=cell, seed=1)
    step = 0.8 * 22 / cell  # the steepest a bilinear cell can be, per pixel
    dx, dy = np.abs(np.diff(a, axis=1)), np.abs(np.diff(a, axis=0))
    assert dx.max() <= step + 1e-9
    assert dy.max() <= step + 1e-9
    # at a cell edge the field moves no more than inside a cell: no seam lines a block grid would leave
    edges = dx[:, cell // 2 - 1 :: cell]
    inside = dx[:, cell // 2 + 3 :: cell]
    assert edges.max() <= inside.max() * 1.01 + 1e-9


def test_segment_dates_puts_it_together() -> None:
    ids_a, ids_b, da, db = _synthetic()
    changed = np.zeros((40, 60), bool)
    changed[10:22, 5:12] = True  # the old building's lot and shadow
    changed[30:38, 25:35] = True  # ground far from any building
    changed[10:20, 40:42] = False  # the new building painted alike: still dated, whole footprint
    out = segment_dates(changed, building_pixels(ids_a, ids_b, da, db), 1950, 1972, cell_px=16)
    assert (out[10:20, 5:10] == 1960.3).all()
    assert (out[10:20, 40:45] == 1965.6).all()
    assert (out[20:22, 5:12] == 1960.3).all()
    assert (out[10:20, 10:12] == 1960.3).all()
    ground = out[30:38, 25:35]
    assert (ground > 1950).all()
    assert (ground < 1972).all()
    unchanged = ~changed & (ids_a == 0) & (ids_b == 0)
    assert np.isnan(out[unchanged]).all()
