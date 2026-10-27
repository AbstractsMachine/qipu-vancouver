import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from qipu_map.classes import SurfaceClass as C
from qipu_map.geo.camera import Canvas
from qipu_map.model import Scene
from qipu_map.render.frames import Frame, FramePlan, plan_frames
from qipu_map.render.job import CyclesSettings, JobInputs, window_ground_box, write_job
from qipu_map.render.look import Light

from .scenes import CAMERA, box_mesh, building, flat, small_scene


def test_window_ground_box_holds_every_point_that_shows_in_the_window() -> None:
    canvas = Canvas.around(CAMERA, (0.0, 0.0, 100.0, 100.0), 30.0)
    frame = Frame("f", 20, 10, 50, 40)
    box = window_ground_box(canvas, frame, 0.0, 30.0)
    rng = np.random.default_rng(0)
    for _ in range(100):
        x, y, z = rng.uniform(-100, 200), rng.uniform(-100, 200), rng.uniform(0, 30)
        u, v = canvas.to_px(x, y, z)
        if frame.x <= u <= frame.x + frame.w and frame.y <= v <= frame.y + frame.h:
            assert box[0] - 1e-9 <= x <= box[2] + 1e-9
            assert box[1] - 1e-9 <= y <= box[3] + 1e-9


def make_job(tmp_path: Path, scene: Scene | None = None) -> tuple[FramePlan, Path, dict[str, Any]]:
    scene = scene or small_scene()
    canvas = Canvas.around(CAMERA, scene.box, 30.0)
    plan = plan_frames(canvas, 128, 96, 8)
    path = write_job(JobInputs(scene, plan, flat(), box_mesh, Light(), CyclesSettings(samples=4)), tmp_path / "job")
    job: dict[str, Any] = json.loads(path.read_text())
    return plan, path, job


def test_job_holds_the_camera_light_and_buildings(tmp_path: Path) -> None:
    plan, _, job = make_job(tmp_path)
    assert job["format"] == "qipu-render-job/1"
    assert job["out_dir"] == ".."
    assert job["canvas"]["width"] == plan.canvas.width
    assert job["light"]["sun_elevation_deg"] == 50.0
    assert job["cycles"] == {"samples": 4, "device": "OPTIX", "filter_width": 1.0, "max_bounces": 8}
    assert [b["index"] for b in job["buildings"]] == [0, 1]
    first = job["buildings"][0]
    assert len(first["vertices"]) == 8
    assert first["classes"][0] == C.ROOF
    assert first["tower"] is False
    assert job["buildings"][1]["tower"] is False
    assert job["trees"] == [{"x": 80.0, "y": 20.0, "z": 0.0, "height": 10.0, "crown": 6.0, "conifer": False}]
    assert [f["name"] for f in job["frames"]] == [f.name for f in plan.frames]


def test_each_frame_gets_its_ground_and_the_buildings_of_its_region(tmp_path: Path) -> None:
    _, path, job = make_job(tmp_path)
    for f in job["frames"]:
        x0, y0, x1, y1 = f["region"]
        assert x0 < x1
        assert y0 < y1
        with np.load(path.parent / f["ground"]) as g:
            assert g["classes"].dtype == np.uint8
            assert g["dem"].ndim == 2
            assert g["classes_origin"][2] == pytest.approx(CAMERA.metres_per_px)
    assert all(set(f["buildings"]) <= {0, 1} for f in job["frames"])
    assert any(f["buildings"] for f in job["frames"])


def test_a_tower_is_marked(tmp_path: Path) -> None:
    _, _, job = make_job(tmp_path, small_scene((building("t", (10, 10, 30, 30), 80),)))
    assert job["buildings"][0]["tower"] is True


def test_job_writing_is_repeatable(tmp_path: Path) -> None:
    _, a, _ = make_job(tmp_path / "a")
    _, b, _ = make_job(tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
