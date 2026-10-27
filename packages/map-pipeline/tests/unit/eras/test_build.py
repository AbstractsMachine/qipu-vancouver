"""The stage's files, end to end on a tiny work folder. The render passes are stubbed; the pyramid writer is real."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from qipu_map import cli
from qipu_map.classes import SurfaceClass
from qipu_map.config import Eras, load_city
from qipu_map.context import Context
from qipu_map.eras import build
from qipu_map.eras.datecodec import NEVER, from_rgb
from qipu_map.eras.rules import EraRules, rules_for_city
from qipu_map.errors import StageError
from qipu_map.imageio import read_image
from qipu_map.model import Raster, Scene
from qipu_map.paths import WorkDir

from .factory import building, old_street, scene

W, H = 600, 300


def _ctx(tmp_path: Path) -> Context:
    city = load_city("vancouver")
    city = replace(city, eras=Eras(today=2026, years=(1950, 1972), footprint_survey_year=2016))
    return Context(city=city, area="west-end", work=WorkDir(tmp_path, city.id, "west-end"))


def _today(ctx: Context) -> None:
    tower = building("tower", 0, 20, 1965, height=60.0)
    out = ctx.work.scene(2026)
    out.mkdir(parents=True)
    scene((*old_street(1905), tower, building("new", 100, 100, 1960))).save(out / "scene.json")
    Raster(0.0, 0.0, 1.0, np.zeros((2, 2), np.float32)).save(out / "terrain.npz")


def test_past_scenes_are_written_with_their_terrain(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _today(ctx)
    paths = build.write_past_scenes(ctx, rules_for_city(ctx.city.id), (1950,))
    assert paths == [ctx.work.scene(1950) / "scene.json"]
    assert (ctx.work.scene(1950) / "terrain.npz").exists()
    text = paths[0].read_text()
    assert '"tower~standin"' in text
    assert '"year":1950' in text


def test_a_built_up_mask_is_read_when_present(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    ctx = _ctx(tmp_path)
    rules = rules_for_city(ctx.city.id)
    assert build.load_evidence(ctx, rules, 1972) is None
    assert build.load_evidence(ctx, rules, 1950) is None
    assert "no built-up mask" in caplog.text
    (ctx.work.ingest / "evidence").mkdir(parents=True)
    Raster(0.0, 0.0, 1.0, np.ones((2, 2), np.float32)).save(ctx.work.ingest / "evidence" / "napl1950.npz")
    found = build.load_evidence(ctx, rules, 1950)
    assert found is not None
    assert found[0].name == "napl1950"


def test_today_must_exist(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with pytest.raises(StageError, match="qipu-map scene"):
        build.load_today(ctx, rules_for_city(ctx.city.id))


def _passes(ctx: Context, coarse: int | None = None) -> dict[tuple[int, str], np.ndarray]:
    """Painted canvases on disk and stubbed render passes: a block that appears in 1972 and a strip of new water."""
    passes: dict[tuple[int, str], np.ndarray] = {}
    scenes = {y: Scene.load(ctx.work.scene(y) / "scene.json") for y in (1950, 1972)}
    for year in (1950, 1972, 2026):
        painted = np.full((H, W, 3), 120, np.uint8)
        ids = np.zeros((H, W), np.uint32)
        cls = np.full((H, W), SurfaceClass.GROUND, np.uint8)
        cls[:, :50] = SurfaceClass.WATER
        painted[:, :50] = 40 + year % 7  # water painted a little differently each year
        if year >= 1972:
            painted[100:150, 300:350] = 230
            names = [
                b.id for b in (scenes[1972].buildings if year == 1972 else build.load_today(ctx, _rules()).buildings)
            ]
            ids[100:150, 300:350] = names.index("tower") + 1
        if year == coarse:  # painted one level up
            painted, ids, cls = painted[::2, ::2], ids[::2, ::2], cls[::2, ::2]
        ctx.work.paint(year).mkdir(parents=True, exist_ok=True)
        Image.fromarray(painted).save(ctx.work.paint(year) / "canvas.png")
        passes[(year, "id")] = ids
        passes[(year, "class")] = cls
    return passes


def _rules() -> EraRules:
    return rules_for_city("ca/vancouver")


def _stub_render(monkeypatch: pytest.MonkeyPatch, passes: dict[tuple[int, str], np.ndarray]) -> None:
    monkeypatch.setattr(build, "load_canvas", lambda render_dir, kind: passes[(int(render_dir.name), kind)])
    monkeypatch.setattr(
        build, "load_plan", lambda _render_dir: SimpleNamespace(canvas=SimpleNamespace(world_px=(0, 0)))
    )


def _dates(path: Path) -> np.ndarray:
    return from_rgb(read_image(path, "RGB"))


def test_layers_and_date_maps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path)
    _today(ctx)
    build.write_past_scenes(ctx, _rules(), (1950, 1972))
    _stub_render(monkeypatch, _passes(ctx))
    out = build.write_layers_and_dates(ctx, _rules())
    work = ctx.work
    assert out == [work.layer(1950), work.layer(1972), work.dates(1950, 1972), work.dates(1972, 2026)]
    assert build.write_layers_and_dates(ctx, _rules()) == []  # nothing changed: nothing written

    layer_1950 = read_image(work.layer(1950))
    assert layer_1950.shape == (H, W, 4)
    alpha = layer_1950[..., 3]
    assert (alpha[110:140, 310:340] == 255).all()  # no tower yet: the old ground shows over today
    assert (alpha[:, :50] == 0).all()  # water then and now: today's water
    assert (alpha[:90] == 0).all()
    assert (alpha[:, 360:] == 0).all()
    layer_1972 = read_image(work.layer(1972))
    assert (layer_1972[..., 3] == 0).all()

    dates = _dates(work.dates(1950, 1972))
    assert dates.shape == (H, W)
    tower = dates[110:140, 310:340]
    tower_dates = 1800 + tower / 100
    assert (tower != NEVER).all()
    assert (tower_dates > 1965).all()
    assert (tower_dates < 1966).all()
    assert dates[250, 200] == NEVER
    assert (_dates(work.dates(1972, 2026)) == NEVER).all()  # nothing changes after 1972
    assert not work.tiles.exists()  # the tiles stage cuts the pyramids


def test_the_command_writes_past_scenes(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _today(ctx)
    assert cli.main(["eras", "scene", "--work", str(tmp_path), "--year", "1930"]) == 0
    assert ctx.work.scene_file(1930).exists()
    assert cli.main(["eras", "scene", "--work", str(tmp_path), "--year", "2026"]) == 2


def test_the_command_runs_the_layers_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake(ctx: Context, rules: EraRules, *, seed: int, force: bool) -> list[Path]:
        seen.append(seed)
        return []

    monkeypatch.setattr("qipu_map.eras.command.write_layers_and_dates", fake)
    assert cli.main(["eras", "layers", "--work", str(tmp_path), "--seed", "7"]) == 0
    assert seen == [7]


def test_a_past_year_painted_one_level_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path)
    _today(ctx)
    build.write_past_scenes(ctx, _rules(), (1950, 1972))
    _stub_render(monkeypatch, _passes(ctx, coarse=1950))
    build.write_layers_and_dates(ctx, _rules())
    layer = read_image(ctx.work.layer(1950))
    assert layer.shape == (H // 2, W // 2, 4)
    assert (layer[55:70, 155:170, 3] == 255).all()
    dates = _dates(ctx.work.dates(1950, 1972))
    assert dates.shape == (H // 2, W // 2)
    assert dates[60, 160] != NEVER
    assert dates[140, 280] == NEVER
