import numpy as np
import pytest

from qipu_map.imageops import (
    blur_u8,
    box_blur,
    dilate,
    erode,
    gaussian,
    halve_rgba,
    label,
    max_filter,
    opening,
    to_rgba,
)


def test_dilate_and_erode_are_squares() -> None:
    m = np.zeros((11, 11), bool)
    m[5, 5] = True
    d = dilate(m, 3)
    assert d.sum() == 49
    assert d[2:9, 2:9].all()
    assert (erode(d, 3) == m).all()
    assert (dilate(m, 0) == m).all()
    assert (erode(m, 0) == m).all()


def test_erosion_at_the_image_edge() -> None:
    full = np.ones((4, 4), bool)
    assert erode(full, 1).all()
    inner = erode(full, 1, edge_is_set=False)
    assert inner.sum() == 4
    assert inner[1:3, 1:3].all()


def test_opening_drops_threads_and_keeps_blobs() -> None:
    m = np.zeros((9, 12), bool)
    m[1:6, 1:6] = True
    m[7, :] = True
    out = opening(m)
    assert (
        out == (np.arange(9)[:, None] < 6) & (np.arange(9)[:, None] >= 1) & (np.arange(12) >= 1) & (np.arange(12) < 6)
    ).all()


def test_max_filter_spreads_the_largest_value_of_any_dtype() -> None:
    a = np.zeros((1, 7), np.int32)
    a[0, 1], a[0, 5] = 2, 3
    assert max_filter(a, 1).tolist() == [[2, 2, 2, 0, 3, 3, 3]]
    f = np.array([[0.5, 0.0, 0.0, 0.25]])
    assert max_filter(f, 2).tolist() == [[0.5, 0.5, 0.5, 0.25]]


def test_blurs_keep_a_flat_field_and_mass() -> None:
    flat = np.full((20, 30), 7.0)
    assert np.allclose(box_blur(flat, 3), 7.0)
    spot = np.zeros((41, 41))
    spot[20, 20] = 1.0
    g = gaussian(spot, 2.0)
    assert g.dtype == np.float64
    assert abs(g.sum() - 1.0) < 1e-9
    assert g[20, 20] == float(np.max(g))
    assert gaussian(spot.astype(np.float32), 1.0).dtype == np.float32
    assert box_blur(spot, 0)[20, 20] == 1.0


def test_blur_u8_keeps_shape_and_type() -> None:
    rgb = np.zeros((10, 10, 3), np.uint8)
    rgb[5, 5] = 255
    out = blur_u8(rgb, 2.0)
    assert out.shape == rgb.shape
    assert out.dtype == np.uint8
    assert 0 < out[5, 5, 0] < 255
    assert blur_u8(rgb[..., 0], 1.0).shape == (10, 10)


def test_label_joins_four_connected_runs() -> None:
    m = np.array(
        [
            [1, 1, 0, 1],
            [0, 1, 0, 1],
            [1, 1, 1, 1],
            [0, 0, 0, 0],
            [1, 0, 1, 0],
        ],
        bool,
    )
    labels, n = label(m)
    assert n == 3
    assert labels[0, 0] == labels[0, 3] == 1  # a U shape is one component, numbered first
    assert labels[4, 0] != labels[4, 2]
    assert label(np.zeros((3, 3), bool))[1] == 0


def test_halving_premultiplies_so_edges_keep_their_colour() -> None:
    image = np.zeros((2, 2, 4), dtype=np.uint8)
    image[0, 0] = (200, 100, 50, 255)
    out = halve_rgba(image)
    assert out.shape == (1, 1, 4)
    assert tuple(out[0, 0]) == (200, 100, 50, 64)


def test_halving_blends_opaque_pixels_evenly() -> None:
    image = np.array(
        [[[0, 0, 0, 255], [100, 100, 100, 255]], [[200, 200, 200, 255], [100, 100, 100, 255]]], dtype=np.uint8
    )
    assert tuple(halve_rgba(image)[0, 0]) == (100, 100, 100, 255)


def test_halving_pads_odd_edges_with_transparency() -> None:
    image = np.full((3, 5, 4), 255, dtype=np.uint8)
    out = halve_rgba(image)
    assert out.shape == (2, 3, 4)
    assert out[0, 0, 3] == 255
    assert out[0, 2, 3] == 128
    assert out[1, 0, 3] == 128
    assert out[1, 2, 3] == 64
    assert (out[..., :3] == 255).all()


def test_halving_a_transparent_block_stays_transparent_black() -> None:
    assert not halve_rgba(np.zeros((4, 4, 4), dtype=np.uint8)).any()


def test_halving_needs_rgba() -> None:
    with pytest.raises(ValueError, match=r"4\) image"):
        halve_rgba(np.zeros((4, 4, 3), dtype=np.uint8))


def test_to_rgba() -> None:
    assert np.min(to_rgba(np.zeros((2, 2, 3), dtype=np.uint8))[..., 3]) == 255
    with pytest.raises(ValueError, match="RGB"):
        to_rgba(np.zeros((2, 2), dtype=np.uint8))
