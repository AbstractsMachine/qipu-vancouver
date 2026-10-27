"""The paint stage end to end on a small made-up canvas, with fake painters (tiles of 128 px at a stride of 64)."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from qipu_map.classes import SurfaceClass as C
from qipu_map.cli import main
from qipu_map.config import Paint
from qipu_map.geo.camera import Canvas, ObliqueCamera
from qipu_map.paint import guards
from qipu_map.paint.backends import RGB, Identity, Painter, Request
from qipu_map.paint.pretone import pretone
from qipu_map.paint.prompts import PromptSet
from qipu_map.paint.run import Inputs, Options, Report, paint_canvas, with_coverage
from qipu_map.paint.tilecache import TileCache
from qipu_map.render.frames import Frame, FramePlan, save_plan
from qipu_map.render.passes import pass_path, write_png

RECIPE = Paint(model="test/model", tile_px=128, stride_px=64, steps=4, guidance=1.0, seed=7)
H, W = 260, 300


def made_up() -> Inputs:
    """Houses on streets, a park, and a small harbour with a boat."""
    classes = np.full((H, W), C.ROAD, np.uint8)
    beauty = np.empty((H, W, 3), np.uint8)
    beauty[:] = (95, 95, 105)
    for y in range(10, 200, 50):
        for x in range(10, 200, 60):
            classes[y : y + 34, x : x + 44] = C.ROOF
            beauty[y : y + 34, x : x + 44] = (150, 75, 55)
            classes[y + 34 : y + 40, x : x + 44] = C.WALL
            beauty[y + 34 : y + 40, x : x + 44] = (190, 170, 150)
    classes[:, 220:] = C.GRASS
    beauty[:, 220:] = (70, 140, 60)
    classes[200:, 120:220] = C.WATER
    beauty[200:, 120:220] = (40, 90, 150)
    classes[225:229, 160:172] = C.ROOF  # a boat
    beauty[225:229, 160:172] = (230, 230, 230)
    return Inputs(beauty, classes, (37, -1290))


def run(
    inputs: Inputs,
    painter: Painter,
    cache: TileCache,
    *,
    year: int = 2026,
    max_tiles: int | None = None,
    colour_restore: bool = False,
) -> tuple[RGB, Report]:
    options = Options(year=year, today=2026, max_tiles=max_tiles, colour_restore=colour_restore)
    return paint_canvas(inputs, RECIPE, painter, prompts=PromptSet.load("vancouver"), cache=cache, options=options)


def test_identity_paints_the_pretoned_render_and_keeps_the_water(tmp_path: Path) -> None:
    inputs = made_up()
    canvas, report = run(inputs, Identity(), TileCache(tmp_path / "tiles"))
    assert canvas.shape == inputs.beauty.shape
    assert canvas.dtype == np.uint8
    water = inputs.classes == C.WATER
    assert (canvas[water] == inputs.beauty[water]).all()
    assert (canvas[225:229, 160:172] == inputs.beauty[225:229, 160:172]).all()  # the boat is the render's
    expect = pretone(inputs.beauty, inputs.classes, inputs.origin)
    land = np.ones((H, W), bool)
    land[195:, 115:225] = False
    assert np.abs(canvas[land].astype(int) - expect[land]).max() <= 1  # one tile's pixels, quilted without a seam
    assert report.tiles == 42
    assert report.painted == 42
    assert report.reused == 0
    assert report.anchors_painted > 0
    assert report.rerolled == 0
    assert sum(report.keys.values()) == 42


def test_a_second_run_reuses_every_tile_and_gives_the_same_bytes(tmp_path: Path) -> None:
    inputs = made_up()
    first, _ = run(inputs, Identity(), TileCache(tmp_path / "tiles"))
    second, report = run(inputs, Identity(), TileCache(tmp_path / "tiles"))
    assert np.array_equal(first, second)
    assert report.painted == 0
    assert report.reused == 42
    assert report.anchors_painted == 0


def test_max_tiles_leaves_the_rest_as_render(tmp_path: Path) -> None:
    _, report = run(made_up(), Identity(), TileCache(tmp_path / "tiles"), max_tiles=4)
    assert report.painted == 4
    assert report.left_as_render == 38


def test_past_years_reuse_unchanged_tiles_from_another_year(tmp_path: Path) -> None:
    inputs = made_up()
    run(inputs, Identity(), TileCache(tmp_path / "2026"))
    _, report = run(inputs, Identity(), TileCache(tmp_path / "1950", also=[tmp_path / "2026"]), year=1950)
    assert 0 < report.reused < report.tiles  # base tiles are the same in 1950; open tiles get the period text


class Melter:
    """Paints every building away on its first try and paints faithfully on a re-roll."""

    name = "melter"
    recipe = "melter"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def paint(self, request: Request) -> RGB:
        self.calls.append(request.noise_key)
        out = Identity().paint(request)
        if request.level == 9 and request.noise_key == "nfC":
            out = np.empty_like(out)
            out[:] = (95, 95, 105)
        return out


def test_a_tile_that_lost_its_buildings_is_rerolled_with_a_new_noise_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guards, "VANISH_MIN_AREA", 500)  # the thresholds are for 1024 px tiles; these are 128 px
    monkeypatch.setitem(guards.THRESHOLDS, "vanish", 1000)
    inputs = made_up()
    melter = Melter()
    canvas, report = run(inputs, melter, TileCache(tmp_path / "tiles"))
    assert report.rerolled > 0
    assert not report.still_flagged
    assert "nfR1" in melter.calls
    assert "nfR2" not in melter.calls
    clean, _ = run(inputs, Identity(), TileCache(tmp_path / "clean"))
    houses = (slice(0, 190), slice(0, 190))
    assert np.abs(canvas[houses].astype(int) - clean[houses]).mean() < 2


def test_colour_restore_option(tmp_path: Path) -> None:
    canvas, _ = run(made_up(), Identity(), TileCache(tmp_path / "tiles"), colour_restore=True)
    assert canvas.shape == (H, W, 3)


@pytest.fixture
def work(tmp_path: Path) -> tuple[Path, Path]:
    """A city file with small tiles, and a render folder holding one frame."""
    city = (Path(__file__).parents[3] / "src/qipu_map/cities/vancouver.toml").read_text()
    city = city.replace("tile_px = 1024", "tile_px = 128").replace("stride_px = 512", "stride_px = 64")
    city_file = tmp_path / "vancouver.toml"
    city_file.write_text(city)
    inputs = made_up()
    render = tmp_path / "work" / "ca-vancouver" / "west-end" / "render" / "2026"
    render.mkdir(parents=True)
    camera = ObliqueCamera(0.0, 30.709, 0.25)
    plan = FramePlan(Canvas(camera, 37 * 0.25, 1290 * 0.25, W, H), (Frame("c000_r000", 0, 0, W, H),), W, H, 0)
    save_plan(plan, 2026, render)
    write_png(pass_path(render, "c000_r000", "beauty"), inputs.beauty)
    write_png(pass_path(render, "c000_r000", "class"), inputs.classes)
    return city_file, tmp_path / "work"


def test_the_command_writes_canvas_tiles_and_report(work: tuple[Path, Path]) -> None:
    city, root = work
    assert main(["paint", "--city", str(city), "--work", str(root), "--backend", "identity"]) == 0
    out = root / "ca-vancouver" / "west-end" / "paint" / "2026"
    assert (out / "canvas.png").is_file()
    assert len(list((out / "tiles").glob("*.png"))) > 42
    report = json.loads((out / "report.json").read_text())
    assert report["painted"] == 42
    assert report["painter"] == "identity"
    assert report["year"] == 2026
    first, written = (out / "canvas.png").read_bytes(), (out / "canvas.png").stat().st_mtime_ns
    assert main(["paint", "--city", str(city), "--work", str(root)]) == 0
    assert (out / "canvas.png").stat().st_mtime_ns == written  # nothing changed: the stage is skipped
    assert main(["paint", "--city", str(city), "--work", str(root), "--force"]) == 0
    assert (out / "canvas.png").read_bytes() == first
    assert json.loads((out / "report.json").read_text())["reused"] == 42
    assert main(["paint", "--city", str(city), "--work", str(root), "--max-tiles", "3"]) == 0
    again = json.loads((out / "report.json").read_text())
    assert again["reused"] == 3
    assert again["left_as_render"] == 39


def test_world_origin_from_the_canvas() -> None:
    canvas = Canvas(ObliqueCamera(0.0, 30.709, 0.25), -10.0, 25.0, 4, 4)
    assert canvas.world_px == (-40, -100)
    with pytest.raises(ValueError, match="whole pixel"):
        _ = replace(canvas, left=0.13).world_px


def test_with_coverage_makes_empty_pixels_transparent() -> None:
    canvas = np.full((2, 3, 3), 90, dtype=np.uint8)
    classes = np.array([[0, 4, 7], [0, 0, 1]], dtype=np.uint8)
    out = with_coverage(canvas, classes)
    assert out.shape == (2, 3, 4)
    assert out[..., 3].tolist() == [[0, 255, 255], [0, 0, 255]]
    assert (out[..., :3] == 90).all()
