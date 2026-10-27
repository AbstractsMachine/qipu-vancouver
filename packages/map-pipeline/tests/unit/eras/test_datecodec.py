import numpy as np
import pytest

from qipu_map.eras.datecodec import (
    NEVER,
    decode_dates,
    decode_png,
    encode_dates,
    encode_png,
    from_rgb,
    is_never,
    reduce_min,
    to_rgb,
)


def test_round_trip_to_a_hundredth_of_a_year() -> None:
    dates = np.array([1800.0, 1961.5, 1972.37, 2026.0, np.nan])
    codes = encode_dates(dates)
    assert codes.dtype == np.uint16
    assert codes[0] == 0
    assert codes[1] == 16150
    assert codes[-1] == NEVER
    back = decode_dates(codes)
    assert np.allclose(back[:-1], dates[:-1], atol=0.005)
    assert np.isnan(back[-1])


def test_dates_out_of_range_are_clamped_not_wrapped() -> None:
    codes = encode_dates(np.array([1700.0, 3000.0]))
    assert codes[0] == 0
    assert codes[1] == NEVER - 1


def test_rgb_layout_is_r_high_g_low_b_zero() -> None:
    rgb = to_rgb(np.array([[16150, NEVER]], np.uint16))
    assert rgb[0, 0].tolist() == [16150 >> 8, 16150 & 255, 0]
    assert rgb[0, 1].tolist() == [255, 255, 0]
    assert from_rgb(rgb).tolist() == [[16150, NEVER]]


def test_png_round_trip_pads_edge_tiles_with_never() -> None:
    tile = np.array([[1, 2], [3, NEVER]], np.uint16)
    back = decode_png(encode_png(tile, tile_size=4))
    assert back.shape == (4, 4)
    assert back[:2, :2].tolist() == tile.tolist()
    assert (back[2:] == NEVER).all()
    assert (back[:, 2:] == NEVER).all()
    assert decode_png(encode_png(tile)).tolist() == tile.tolist()


def test_reduce_min_keeps_the_earliest_date() -> None:
    codes = np.array([[5, NEVER, NEVER], [9, 7, 3], [NEVER, NEVER, 8]], np.uint16)
    out = reduce_min(codes)
    assert out.tolist() == [[5, 3], [NEVER, 8]]
    assert reduce_min(np.full((4, 4), NEVER, np.uint16)).tolist() == [[NEVER] * 2] * 2


@pytest.mark.parametrize(("value", "empty"), [(NEVER, True), (100, False)])
def test_is_never(value: int, empty: bool) -> None:
    tile = np.full((3, 3), NEVER, np.uint16)
    tile[1, 1] = value
    assert is_never(tile) is empty
