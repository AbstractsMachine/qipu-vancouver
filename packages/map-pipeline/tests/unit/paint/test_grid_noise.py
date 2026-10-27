import numpy as np
import pytest

from qipu_map.paint.grid import Grid, Tile, crop_reflect, seed_for
from qipu_map.paint.noise import CHUNK, noise_field


def covered(grid: Grid) -> np.ndarray:
    hits = np.zeros((grid.height, grid.width), int)
    ox, oy = grid.origin
    for t in grid.tiles():
        x0, y0 = max(0, t.x - ox), max(0, t.y - oy)
        x1, y1 = min(grid.width, t.x - ox + grid.tile), min(grid.height, t.y - oy + grid.tile)
        hits[y0:y1, x0:x1] += 1
    return hits


@pytest.mark.parametrize("origin", [(0, 0), (37, -1290), (-512, 513)])
def test_tiles_cover_the_canvas_four_times_at_half_stride(origin: tuple[int, int]) -> None:
    grid = Grid(tile=1024, stride=512, origin=origin, width=1700, height=1300)
    hits = covered(grid)
    assert hits.min() == 4
    assert hits.max() == 4
    assert all(t.x % 512 == 0 and t.y % 512 == 0 for t in grid.tiles())
    assert len(set(grid.tiles())) == len(grid.tiles())


def test_tiles_are_keyed_to_the_world_not_the_canvas() -> None:
    a = Grid(1024, 512, (0, 0), 3000, 2000)
    b = Grid(1024, 512, (1000, 600), 1000, 800)  # a smaller area inside the first
    assert set(b.tiles()) <= set(a.tiles())
    assert seed_for(512, 1024, 7) == seed_for(512, 1024, 7) != seed_for(1024, 512, 7)
    assert Tile(512, 1024).key == "512_1024"


def test_stride_must_fit() -> None:
    with pytest.raises(ValueError, match="stride"):
        Grid(64, 128, (0, 0), 10, 10)


def test_crop_reflect_mirrors_at_the_edges() -> None:
    img = np.arange(5 * 4).reshape(4, 5)
    inside = crop_reflect(img, 1, 1, 3, 2)
    assert (inside == img[1:3, 1:4]).all()
    left = crop_reflect(img, -2, 0, 4, 1)
    assert left.tolist() == [[1, 0, 0, 1]]
    big = crop_reflect(img, -7, -9, 20, 20)
    assert big.shape == (20, 20)
    assert set(np.unique(big)) <= set(img.ravel())
    assert (crop_reflect(np.ones((1, 1)), -3, -3, 7, 7) == 1).all()


def test_noise_is_the_same_where_two_windows_overlap() -> None:
    a = noise_field("nfC", 9, 0, 0, n=64, channels=4)
    b = noise_field("nfC", 9, 32, 16, n=64, channels=4)  # translated by half a tile
    assert np.array_equal(a[:, 16:, 32:], b[:, :48, :32])
    assert not np.array_equal(a, noise_field("nfR1", 9, 0, 0, n=64, channels=4))
    assert not np.array_equal(a, noise_field("nfC", 8, 0, 0, n=64, channels=4))
    odd = noise_field("nfC", 9, -5, 3, n=CHUNK + 3, channels=2)
    assert np.array_equal(odd[:, :, 5:], noise_field("nfC", 9, 0, 3, n=CHUNK + 3, channels=2)[:, :, : CHUNK - 2])
    assert abs(float(a.mean())) < 0.05
    assert 0.9 < float(a.std()) < 1.1
