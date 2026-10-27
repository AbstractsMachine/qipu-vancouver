import numpy as np

from qipu_map.tiles.images import decode, encode_webp, is_near_black


def test_webp_round_trip_keeps_alpha_and_colour() -> None:
    tile = np.zeros((64, 64, 4), dtype=np.uint8)
    tile[:, :32] = (120, 160, 90, 255)
    back = decode(encode_webp(tile))
    assert back.shape == (64, 64, 4)
    assert (back[:, 40:, 3] == 0).all()
    assert (back[:, :28, 3] == 255).all()
    assert np.abs(back[:, :28, :3].astype(int) - (120, 160, 90)).max() <= 4


def test_opaque_tiles_are_written_without_alpha() -> None:
    tile = np.full((32, 32, 4), 255, dtype=np.uint8)
    data = encode_webp(tile)
    assert b"ALPH" not in data
    assert b"VP8X" not in data
    assert (decode(data)[..., 3] == 255).all()


def test_near_black_tiles_are_flagged_and_empty_ones_are_not() -> None:
    tile = np.zeros((8, 8, 4), dtype=np.uint8)
    assert not is_near_black(tile)
    tile[..., 3] = 255
    assert is_near_black(tile)
    tile[0, 0, 1] = 40
    assert not is_near_black(tile)
