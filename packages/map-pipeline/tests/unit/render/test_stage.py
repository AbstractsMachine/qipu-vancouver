import json
from dataclasses import replace
from pathlib import Path

import pytest

from qipu_map.cli import main
from qipu_map.render import blender_backend
from qipu_map.render.mosaic import load_canvas
from qipu_map.render.stage import RenderSettings, render_year

from .scenes import CAMERA, box_mesh, building, flat, small_scene

SMALL = RenderSettings(frame_w=128, frame_h=96, overlap_px=8)


def write_scene(scene_dir: Path, with_terrain: bool = True) -> None:
    scene_dir.mkdir(parents=True, exist_ok=True)
    small_scene().save(scene_dir / "scene.json")
    if with_terrain:
        flat(1.0).save(scene_dir / "terrain.npz")


def test_preview_render_writes_frames_and_passes(tmp_path: Path) -> None:
    write_scene(tmp_path / "scene")
    out = tmp_path / "render"
    assert render_year(tmp_path / "scene", out, CAMERA, SMALL, box_mesh)
    plan = json.loads((out / "frames.json").read_text())
    names = [f["name"] for f in plan["frames"]]
    assert len(names) > 1
    for n in names:
        assert all((out / f"{n}.{k}.png").is_file() for k in ("beauty", "class", "id"))
    ids = load_canvas(out, "id")
    assert ids.shape == (plan["canvas"]["height"], plan["canvas"]["width"])
    assert set(ids.ravel().tolist()) == {0, 1, 2}


def test_an_unchanged_scene_is_not_rendered_again(tmp_path: Path) -> None:
    write_scene(tmp_path / "scene")
    out = tmp_path / "render"
    assert render_year(tmp_path / "scene", out, CAMERA, SMALL, box_mesh)
    assert not render_year(tmp_path / "scene", out, CAMERA, SMALL, box_mesh)
    assert render_year(tmp_path / "scene", out, CAMERA, replace(SMALL, overlap_px=16), box_mesh)


def test_a_scene_without_terrain_renders_on_level_ground(tmp_path: Path) -> None:
    write_scene(tmp_path / "scene", with_terrain=False)
    assert render_year(tmp_path / "scene", tmp_path / "render", CAMERA, SMALL, box_mesh)


def test_the_blender_backend_writes_a_job_and_runs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_scene(tmp_path / "scene")
    seen: list[tuple[Path, list[str]]] = []
    monkeypatch.setattr(blender_backend, "render_frames", lambda job, frames: seen.append((job, frames)))
    out = tmp_path / "render"
    render_year(tmp_path / "scene", out, CAMERA, replace(SMALL, backend="blender"), box_mesh)
    job, frames = seen[0]
    assert job == out / "job" / "job.json"
    assert job.is_file()
    assert frames == [f["name"] for f in json.loads((out / "frames.json").read_text())["frames"]]


def test_the_command_renders_every_year_with_a_scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "ca-vancouver" / "west-end"
    for year in (1972, 2026):
        write_scene(base / "scene" / str(year))
    done: list[tuple[int, str]] = []

    def fake(s: Path, o: Path, c: object, st: object, m: object, *, canvas_from: Path) -> None:
        done.append((int(s.name), canvas_from.name))

    monkeypatch.setattr("qipu_map.render.command.render_year", fake)
    assert main(["render", "--work", str(tmp_path), "--samples", "8", "--device", "metal"]) == 0
    assert done == [(1972, "2026"), (2026, "2026")]


def test_every_year_shares_todays_canvas(tmp_path: Path) -> None:
    today, past = tmp_path / "scene" / "2026", tmp_path / "scene" / "1930"
    today.mkdir(parents=True)
    past.mkdir(parents=True)
    small_scene((building("a", (20, 20, 40, 30), 12), building("tower", (60, 50, 70, 60), 90))).save(
        today / "scene.json"
    )
    small_scene((building("a", (20, 20, 40, 30), 12),), year=1930).save(past / "scene.json")
    for year, scene_dir in ((2026, today), (1930, past)):
        render_year(scene_dir, tmp_path / "render" / str(year), CAMERA, SMALL, box_mesh, canvas_from=today)
    a = json.loads((tmp_path / "render" / "2026" / "frames.json").read_text())
    b = json.loads((tmp_path / "render" / "1930" / "frames.json").read_text())
    assert a["canvas"] == b["canvas"]
    assert a["frames"] == b["frames"]


def test_the_command_needs_todays_scene(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_scene(tmp_path / "ca-vancouver" / "west-end" / "scene" / "1972")
    assert main(["render", "--work", str(tmp_path)]) == 2
    assert "today's scene" in capsys.readouterr().err


def test_the_command_says_when_there_is_nothing_to_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", "--work", str(tmp_path)]) == 2
    assert "qipu-map scene" in capsys.readouterr().err


def test_a_changed_past_scene_or_a_changed_canvas_renders_again(tmp_path: Path) -> None:
    today, past = tmp_path / "scene" / "2026", tmp_path / "scene" / "1930"
    write_scene(today)
    past.mkdir(parents=True)
    small_scene((building("a", (20, 20, 40, 30), 12),), year=1930).save(past / "scene.json")
    out = tmp_path / "render" / "1930"

    def render() -> bool:
        return render_year(past, out, CAMERA, SMALL, box_mesh, canvas_from=today)

    assert render()
    assert not render()
    small_scene((building("a", (20, 20, 40, 30), 15),), year=1930).save(past / "scene.json")
    assert render()
    assert not render()
    small_scene((building("a", (20, 20, 40, 30), 12), building("tall", (60, 50, 70, 60), 80))).save(
        today / "scene.json"
    )
    assert render()
