from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from qipu_map.imageops import halve_rgba
from qipu_map.tiles.have import unpack_have
from qipu_map.tiles.images import decode, encode_webp
from qipu_map.tiles.pyramid import Pyramid, cut_tile, is_transparent, level_size, write_pyramid, zmax_for


@pytest.mark.parametrize(
    ("w", "h", "tile", "z"),
    [
        (1, 1, 512, 0),
        (512, 512, 512, 0),
        (513, 10, 512, 1),
        (1024, 1024, 512, 1),
        (1025, 3, 512, 2),
        (2390, 1720, 512, 3),
    ],
)
def test_zmax_is_the_halvings_to_fit_one_tile(w: int, h: int, tile: int, z: int) -> None:
    assert zmax_for(w, h, tile) == z
    assert max(level_size(w, h, z, 0)) <= tile


def test_zmax_rejects_empty_sizes() -> None:
    with pytest.raises(ValueError, match="positive"):
        zmax_for(0, 10, 512)


def test_level_sizes_round_up_like_repeated_halving() -> None:
    w, h, zmax = 2390, 1721, 3
    assert level_size(w, h, zmax, 3) == (2390, 1721)
    assert level_size(w, h, zmax, 2) == (1195, 861)
    assert level_size(w, h, zmax, 1) == (598, 431)
    assert level_size(w, h, zmax, 0) == (299, 216)
    with pytest.raises(ValueError, match="outside"):
        level_size(w, h, zmax, 4)


def test_edge_tiles_are_full_size_and_transparent_past_the_canvas() -> None:
    level = np.full((5, 7, 4), 200, dtype=np.uint8)
    tile = cut_tile(level, 1, 1, 4)
    assert tile.shape == (4, 4, 4)
    assert (tile[:1, :3] == 200).all()
    assert (tile[1:, :] == 0).all()
    assert (tile[:, 3:] == 0).all()
    assert cut_tile(level, 0, 0, 4).base is not None


def test_edge_tiles_can_pad_with_another_value() -> None:
    level = np.zeros((3, 3, 3), dtype=np.uint8)
    assert (cut_tile(level, 0, 0, 4, fill=255)[3] == 255).all()


def test_transparent_means_no_visible_pixel() -> None:
    tile = np.zeros((4, 4, 4), dtype=np.uint8)
    assert is_transparent(tile)
    tile[2, 3, 3] = 1
    assert not is_transparent(tile)
    assert not is_transparent(np.zeros((4, 4, 3), dtype=np.uint8))


def _png(tile: NDArray[np.uint8]) -> bytes:
    return tile.tobytes()


def test_pyramid_writes_every_level_and_skips_empty_tiles(tmp_path: Path) -> None:
    image = np.zeros((10, 20, 4), dtype=np.uint8)
    image[:4, :4] = (10, 20, 30, 255)
    image[8:, 17:] = (90, 80, 70, 255)
    pyr = write_pyramid(image, tmp_path, tile_size=4, encode=_png, reduce=halve_rgba, suffix=".raw")
    assert pyr.zmax == 3
    assert pyr.tiles[3] == {(0, 0), (4, 2)}
    assert pyr.tiles[2] == {(0, 0), (2, 1)}
    assert pyr.tiles[0] == {(0, 0)}
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.raw"))
    assert files == sorted(pyr.paths())
    assert (tmp_path / "3" / "4" / "2.raw").read_bytes() == cut_tile(image, 4, 2, 4).tobytes()


def test_pyramid_round_trips_through_its_index(tmp_path: Path) -> None:
    image = np.zeros((9, 9, 4), dtype=np.uint8)
    image[5:, :3, 3] = 255
    pyr = write_pyramid(image, tmp_path, tile_size=4, encode=_png, reduce=halve_rgba, suffix=".raw")
    again = Pyramid.load(tmp_path)
    assert again == Pyramid(pyr.zmax, 4, ".raw", {z: t for z, t in pyr.tiles.items() if t})
    for z, h in pyr.have().items():
        assert unpack_have(h) == pyr.tiles[int(z)]


def test_a_rerun_removes_tiles_it_no_longer_writes(tmp_path: Path) -> None:
    image = np.full((8, 8, 4), 255, dtype=np.uint8)
    write_pyramid(image, tmp_path, tile_size=4, encode=_png, reduce=halve_rgba, suffix=".raw")
    image[:, 4:] = 0
    pyr = write_pyramid(image, tmp_path, tile_size=4, encode=_png, reduce=halve_rgba, suffix=".raw")
    assert not (tmp_path / "1" / "1" / "0.raw").exists()
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.raw")) == sorted(pyr.paths())


def test_a_reducer_with_the_wrong_size_is_caught(tmp_path: Path) -> None:
    image = np.full((8, 8, 4), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="expected"):
        write_pyramid(image, tmp_path, tile_size=4, encode=_png, reduce=lambda a: a[:3, :3], suffix=".raw")


def test_same_image_same_bytes(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    image = rng.integers(0, 256, (40, 50, 4), dtype=np.uint8)
    a = write_pyramid(image, tmp_path / "a", tile_size=16, encode=encode_webp, reduce=halve_rgba, suffix=".webp")
    b = write_pyramid(image, tmp_path / "b", tile_size=16, encode=encode_webp, reduce=halve_rgba, suffix=".webp")
    assert list(a.paths()) == list(b.paths())
    for p in a.paths():
        assert (tmp_path / "a" / p).read_bytes() == (tmp_path / "b" / p).read_bytes()
    assert decode((tmp_path / "a" / next(a.paths())).read_bytes()).shape == (16, 16, 4)
