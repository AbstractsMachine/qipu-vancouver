import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from qipu_map.imageio import image_size, png_bytes, read_image, write_png


def test_png_round_trip_in_each_mode(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    for shape in ((5, 7), (5, 7, 3), (5, 7, 4)):
        a = rng.integers(0, 256, shape, dtype=np.uint8)
        path = tmp_path / f"{len(shape)}-{shape[-1]}.png"
        write_png(path, a)
        assert (read_image(path) == a).all()
    assert image_size(tmp_path / "3-3.png") == (7, 5)


def test_compression_changes_bytes_not_pixels() -> None:
    a = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
    fast, small = png_bytes(a, "fast"), png_bytes(a, "small")
    assert len(small) <= len(fast)
    assert (read_image(io.BytesIO(fast)) == read_image(io.BytesIO(small))).all()
    assert png_bytes(a) == png_bytes(a)


def test_mode_on_reading(tmp_path: Path) -> None:
    rgb = np.zeros((2, 2, 3), np.uint8)
    path = tmp_path / "x.png"
    write_png(path, rgb)
    assert (read_image(path, "RGBA")[..., 3] == 255).all()
    assert read_image(path, "L").shape == (2, 2)
    Image.fromarray(np.zeros((2, 2), np.uint8), "L").convert("P").save(tmp_path / "p.png", transparency=0)
    assert read_image(tmp_path / "p.png").shape == (2, 2, 4)


def test_write_png_refuses_odd_shapes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="an image is"):
        write_png(tmp_path / "x.png", np.zeros((2, 2, 2), np.uint8))
