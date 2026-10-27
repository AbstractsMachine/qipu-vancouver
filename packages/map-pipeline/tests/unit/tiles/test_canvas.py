from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from qipu_map.cli import main
from qipu_map.imageio import read_image
from qipu_map.paths import WorkDir
from qipu_map.tiles.canvas import TileError, TileJob, dark_tiles, layer_zoom, tile_job
from qipu_map.tiles.images import decode
from qipu_map.tiles.pyramid import Pyramid


def _save(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path)
    return path


def _painted(w: int, h: int, alpha: bool = True) -> np.ndarray:
    rng = np.random.default_rng(3)
    img = rng.integers(60, 200, (h, w, 4 if alpha else 3), dtype=np.uint8)
    if alpha:
        img[..., 3] = 255
        img[: h // 3, : w // 3, 3] = 0
    return img


def test_layer_zoom_finds_the_matching_level() -> None:
    assert layer_zoom((1100, 700), (1100, 700), 256) == 3
    assert layer_zoom((1100, 700), (275, 175), 256) == 1
    with pytest.raises(TileError, match="none of the zoom levels"):
        layer_zoom((1100, 700), (500, 300), 256)


def test_rgb_canvas_loads_opaque(tmp_path: Path) -> None:
    img = read_image(_save(tmp_path / "c.png", _painted(10, 8, alpha=False)), "RGBA")
    assert img.shape == (8, 10, 4)
    assert (img[..., 3] == 255).all()


def test_dark_tiles_are_found() -> None:
    img = _painted(64, 32)
    img[:, 32:, :3] = 3
    assert dark_tiles(img, 32) == [(1, 0)]


def test_tile_layer_writes_webp_and_skips_when_unchanged(tmp_path: Path) -> None:
    img = _painted(300, 200)
    img[:128, :128, 3] = 0
    canvas = _save(tmp_path / "canvas.png", img)
    layer = TileJob("today", canvas, tmp_path / "out")
    pyr = tile_job(layer, tile_size=128)
    assert pyr.zmax == 2
    assert (0, 0) not in pyr.tiles[2]
    first = decode((tmp_path / "out" / "2" / "2" / "1.webp").read_bytes())
    assert first.shape == (128, 128, 4)
    assert (first[72:, :, 3] == 0).all()
    assert (first[:, 44:, 3] == 0).all()
    stamp = (tmp_path / "out" / ".stamp").stat().st_mtime_ns
    assert tile_job(layer, tile_size=128) == Pyramid.load(tmp_path / "out")
    assert (tmp_path / "out" / ".stamp").stat().st_mtime_ns == stamp


def test_tile_layer_refuses_black_tiles_and_misaligned_years(tmp_path: Path) -> None:
    img = _painted(200, 100)
    img[:, :100, :3] = 0
    with pytest.raises(TileError, match="near-black"):
        tile_job(TileJob("today", _save(tmp_path / "a.png", img), tmp_path / "a"), tile_size=100)
    small = _save(tmp_path / "b.png", _painted(90, 50))
    with pytest.raises(TileError, match="zoom levels"):
        tile_job(TileJob("year 1950", small, tmp_path / "b"), tile_size=100, today_size=(200, 100))


def test_command_tiles_today_and_the_years_that_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = WorkDir(tmp_path, "ca/vancouver", "west-end")
    _save(work.canvas(2026), _painted(1100, 600))
    _save(work.layer(1950), _painted(550, 300))
    dates = np.zeros((300, 550, 3), np.uint8)
    dates[..., :2] = 255
    dates[10:20, 10:20, :2] = (63, 0)
    _save(work.dates(1950, 1972), dates)
    (work.year_tiles(1900)).mkdir(parents=True)
    assert main(["tiles", "--work", str(tmp_path)]) == 0
    assert Pyramid.load(work.today_tiles()).zmax == 2
    assert Pyramid.load(work.year_tiles(1950)).zmax == 1
    switch = Pyramid.load(work.switch_tiles(1950, 1972))
    assert switch.suffix == ".png"
    assert switch.tiles[1] == frozenset({(0, 0)})
    assert not work.year_tiles(1930).exists()
    assert not work.year_tiles(1900).exists()


def test_command_needs_a_painted_canvas(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tiles", "--work", str(tmp_path)]) == 2
    assert "run `qipu-map paint` first" in capsys.readouterr().err


def test_command_reports_bad_canvases(tmp_path: Path) -> None:
    work = WorkDir(tmp_path, "ca/vancouver", "west-end")
    _save(work.canvas(2026), _painted(1100, 600))
    _save(work.layer(1950), _painted(500, 300))
    with pytest.raises(TileError, match="zoom levels"):
        tile_job(TileJob("year 1950", work.layer(1950), work.year_tiles(1950)), tile_size=512, today_size=(1100, 600))
    assert main(["tiles", "--work", str(tmp_path)]) == 2
