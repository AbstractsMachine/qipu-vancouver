"""The render stage for one year: plan the frames, draw them with a backend, write frames.json last.

Inputs: `scene/<year>/scene.json` and its terrain file. Outputs in `render/<year>/`: `frames.json` and, per frame,
`<name>.beauty.png`, `<name>.class.png`, `<name>.id.png` (see `passes`). The stage is skipped when the scene, the
terrain and the settings are unchanged since the last finished run.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from qipu_map import cache
from qipu_map.geo.camera import Canvas, ObliqueCamera
from qipu_map.model import Raster, Scene
from qipu_map.render import blender_backend
from qipu_map.render.frames import FramePlan, plan_frames, save_plan
from qipu_map.render.ground import flat_terrain
from qipu_map.render.job import CyclesSettings, JobInputs, write_job
from qipu_map.render.look import Light
from qipu_map.render.meshes import Mesher
from qipu_map.render.passes import pass_path, write_png
from qipu_map.render.preview import PreviewScene

log = logging.getLogger(__name__)

Backend = Literal["preview", "blender"]
STAGE = "render"
VERSION = 1


@dataclass(frozen=True)
class RenderSettings:
    """The render stage's settings: backend, frame size and overlap in pixels, light and Cycles options."""

    backend: Backend = "preview"
    frame_w: int = 2048
    frame_h: int = 1536
    overlap_px: int = 64
    light: Light = field(default_factory=Light)
    cycles: CyclesSettings = field(default_factory=CyclesSettings)


def load_terrain(scene: Scene, scene_dir: Path) -> Raster:
    path = scene_dir / scene.terrain_file if scene.terrain_file else None
    if path is None or not path.is_file():
        log.warning("no terrain file for %s; using level ground", scene_dir)
        return flat_terrain(scene.box)
    return Raster.load(path)


def scene_canvas(scene: Scene, camera: ObliqueCamera, terrain: Raster) -> Canvas:
    """The canvas that shows the scene's box with its tallest roof and highest ground."""
    tops = [b.ground_m + b.height_m for b in scene.buildings] + [float(np.max(terrain.data)), 0.0]
    return Canvas.around(camera, scene.box, max(tops))


def render_year(
    scene_dir: Path,
    out_dir: Path,
    camera: ObliqueCamera,
    settings: RenderSettings,
    mesher: Mesher,
    *,
    canvas_from: Path | None = None,
) -> bool:
    """Render one year's scene. Returns False when the cache says nothing changed.

    `canvas_from` is the scene folder that sets the canvas, normally today's: every year of an area shares one canvas
    and one frame grid, so the era stage can compare years pixel for pixel and the tiles line up. A year's own tallest
    building does not move it.
    """
    scene_file = scene_dir / "scene.json"
    scene = Scene.load(scene_file)
    canvas_dir = canvas_from if canvas_from is not None else scene_dir
    canvas_scene = Scene.load(canvas_dir / "scene.json") if canvas_dir != scene_dir else scene
    files = {
        scene_file,
        scene_dir / scene.terrain_file,
        canvas_dir / "scene.json",
        canvas_dir / canvas_scene.terrain_file,
    }
    inputs = sorted(p for p in files if p.is_file())
    params = {
        "version": VERSION,
        "camera": asdict(camera),
        "settings": asdict(settings),
        "canvas_from": canvas_dir.name,
    }
    key = cache.stage_key(STAGE, inputs, params)
    if cache.is_fresh(out_dir, key):
        log.info("render %s: up to date", scene.year)
        return False
    terrain = load_terrain(scene, scene_dir)
    canvas_terrain = terrain if canvas_dir == scene_dir else load_terrain(canvas_scene, canvas_dir)
    canvas = scene_canvas(canvas_scene, camera, canvas_terrain)
    plan = plan_frames(canvas, settings.frame_w, settings.frame_h, settings.overlap_px)
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("render %s: canvas %dx%d, %d frames", scene.year, plan.canvas.width, plan.canvas.height, len(plan.frames))
    if settings.backend == "preview":
        _render_preview(PreviewScene.build(scene, plan.canvas, terrain, mesher, settings.light), plan, out_dir)
    else:
        job = write_job(JobInputs(scene, plan, terrain, mesher, settings.light, settings.cycles), out_dir / "job")
        blender_backend.render_frames(job, [f.name for f in plan.frames])
    save_plan(plan, scene.year, out_dir)
    cache.mark_done(out_dir, key)
    return True


def _render_preview(drawn: PreviewScene, plan: FramePlan, out_dir: Path) -> None:
    for frame in plan.frames:
        passes = drawn.render(frame)
        write_png(pass_path(out_dir, frame.name, "beauty"), passes.beauty)
        write_png(pass_path(out_dir, frame.name, "class"), passes.classes)
        write_png(pass_path(out_dir, frame.name, "id"), passes.ids)
