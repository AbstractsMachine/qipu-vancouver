import numpy as np
import pytest

from qipu_map.classes import SurfaceClass
from qipu_map.eras.compare import changed_mask, composite, shrink
from qipu_map.eras.layer import past_layer
from qipu_map.imageops import to_rgba


def _canvas(value: int, shape: tuple[int, int] = (40, 40)) -> np.ndarray:
    return np.full((*shape, 3), value, np.uint8)


def test_unchanged_pixels_are_fully_transparent() -> None:
    cls = np.full((40, 40), SurfaceClass.GROUND, np.uint8)
    layer = past_layer(_canvas(100), _canvas(100), cls, cls)
    assert layer.shape == (40, 40, 4)
    assert not layer.any()


def test_painting_grain_is_not_a_change() -> None:
    rng = np.random.default_rng(0)
    noisy = np.clip(100 + rng.integers(-15, 16, (40, 40, 3)), 0, 255).astype(np.uint8)
    assert not changed_mask(noisy, _canvas(100)).any()


def test_a_changed_block_is_opaque_inside_and_eases_at_its_edge() -> None:
    painted = _canvas(100)
    painted[10:30, 10:30] = 200
    cls = np.full((40, 40), SurfaceClass.GROUND, np.uint8)
    layer = past_layer(painted, _canvas(100), cls, cls)
    alpha = layer[..., 3]
    assert (alpha[15:25, 15:25] == 255).all()
    assert (layer[15:25, 15:25, :3] == 200).all()
    assert alpha[0, 0] == 0
    assert (layer[alpha == 0, :3] == 0).all()
    edge = alpha[20, 6:15]
    assert 0 < int(np.min(edge[edge > 0])) < 255


def test_water_over_todays_water_shows_today() -> None:
    painted = _canvas(100)
    painted[:, :20] = 30  # a different blue on the left half
    era_cls = np.full((40, 40), SurfaceClass.WATER, np.uint8)
    today_cls = np.full((40, 40), SurfaceClass.GROUND, np.uint8)
    today_cls[:, :10] = SurfaceClass.WATER
    alpha = past_layer(painted, _canvas(100), era_cls, today_cls)[..., 3]
    assert (alpha[:, :10] == 0).all()  # water then and now: today's water
    assert (alpha[5:35, 12:17] > 0).all()  # water then, land now: the old shore shows


def test_unpainted_pixels_of_the_past_year_stay_transparent() -> None:
    painted = to_rgba(_canvas(200))
    painted[:, :20, 3] = 0
    cls = np.zeros((40, 40), np.uint8)
    alpha = past_layer(painted, _canvas(100), cls, cls)[..., 3]
    assert (alpha[:, :20] == 0).all()
    assert (alpha[5:35, 25:35] == 255).all()


def test_sizes_must_agree() -> None:
    with pytest.raises(ValueError, match="class passes"):
        past_layer(_canvas(1), _canvas(1), np.zeros((3, 3), np.uint8), np.zeros((40, 40), np.uint8))
    with pytest.raises(ValueError, match="differ in size"):
        changed_mask(_canvas(1), _canvas(1, (3, 3)))
    with pytest.raises(ValueError, match="RGB or RGBA"):
        to_rgba(np.zeros((3, 3), np.uint8))


def test_composite_is_what_the_viewer_shows() -> None:
    layer = np.zeros((2, 2, 4), np.uint8)
    layer[0, 0] = (200, 0, 0, 255)
    out = composite(layer, _canvas(100, (2, 2)))
    assert out[0, 0].tolist() == [200, 0, 0, 255]
    assert out[1, 1].tolist() == [100, 100, 100, 255]


def test_shrink_to_a_coarser_level() -> None:
    img = np.zeros((5, 7, 3), np.uint8)
    img[:2, :2] = 200
    small = shrink(img, (4, 3))
    assert small.shape == (3, 4, 4)
    assert small[0, 0].tolist() == [200, 200, 200, 255]
    labels = np.arange(35).reshape(5, 7)
    assert shrink(labels, (4, 3), labels=True).tolist() == [[0, 2, 4, 6], [14, 16, 18, 20], [28, 30, 32, 34]]
    assert shrink(img, (7, 5)) is img
    with pytest.raises(ValueError, match="pyramid level"):
        shrink(img, (3, 3))


def test_shrink_does_not_darken_the_edge_of_what_is_painted() -> None:
    img = np.zeros((2, 2, 4), np.uint8)
    img[0, 0] = (200, 180, 160, 255)
    assert shrink(img, (1, 1))[0, 0].tolist() == [200, 180, 160, 64]
