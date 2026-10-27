import numpy as np

from qipu_map.classes import SurfaceClass as C
from qipu_map.paint.protect import on_water, protect
from qipu_map.paint.quilt import band_for, join, quilt, seam, seam_weights


def test_band_matches_the_live_quilt() -> None:
    assert band_for(1024, 512) == 200
    assert band_for(1024, 1024) == 0
    assert band_for(64, 32) == 7


def test_seam_follows_the_cheap_column() -> None:
    cost = np.ones((30, 9), np.float32)
    cost[:, 6] = 0.0
    assert (seam(cost) == 6).all()
    cost[15:, 6], cost[15:, 5] = 1.0, 0.0
    path = seam(cost)
    assert (np.abs(np.diff(path)) <= 1).all()
    assert path[0] == 6
    assert path[-1] == 5


def test_feather_weights_sum_to_one_and_ramp() -> None:
    w = seam_weights(np.full(4, 10), 21, feather=6)
    assert (w[:, :4] == 0).all()
    assert (w[:, 16:] == 1).all()
    assert np.allclose(w + (1 - w), 1.0)
    assert (np.diff(w, axis=1) >= 0).all()


def test_identical_tiles_quilt_without_a_seam() -> None:
    rng = np.random.default_rng(3)
    world = rng.uniform(0, 255, (64 + 3 * 32, 64 + 4 * 32, 3)).astype(np.float32)
    xs, ys = [0, 32, 64, 96, 128], [0, 32, 64, 96]

    def load(x: int, y: int) -> np.ndarray:
        return world[y : y + 64, x : x + 64]

    out = quilt(xs, ys, 64, load, np.zeros(world.shape[:2], bool))
    assert out.shape == world.shape
    assert np.allclose(out, world)


def test_seam_avoids_facades() -> None:
    a = np.zeros((40, 20, 3), np.float32)
    b = np.full((40, 20, 3), 100.0, np.float32)
    walls = np.ones((40, 20), bool)
    walls[:, 3] = False  # the only column without a facade
    out = join(a, b, walls)
    assert (out[:, :3] < 50).all()
    assert (out[:, 4:] > 50).all()


def test_water_and_what_floats_on_it_come_from_the_render() -> None:
    classes = np.full((80, 80), C.WATER, np.uint8)
    classes[:, :20] = C.GROUND  # the shore, touching the edge: land, not protected
    classes[40:44, 50:60] = C.ROOF  # a boat in the bay
    boat = on_water(classes)
    assert boat[40:44, 50:60].all()
    assert boat.sum() == 40
    painted = np.full((80, 80, 3), 10, np.uint8)
    render = np.full((80, 80, 3), 200, np.uint8)
    out = protect(painted, render, classes)
    assert (out[classes == C.WATER] == 200).all()
    assert (out[40:44, 50:60] == 200).all()
    assert (out[:, :15] == 10).all()
    assert 10 < int(out[10, 19, 0]) < 200  # a soft rim beside the water
    keep = np.zeros((80, 80), bool)
    keep[0:5, 0:5] = True
    assert (protect(painted, render, classes, keep)[0:5, 0:5] == 200).all()


def test_no_water_no_change() -> None:
    classes = np.full((10, 10), C.GROUND, np.uint8)
    assert not on_water(classes).any()
    classes[:] = C.WATER
    assert not on_water(classes).any()
