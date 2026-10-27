"""The job file Blender reads: everything a frame needs, with no Python objects and no paths outside the job folder.

`job/job.json` holds the canvas, the light, the render settings, each frame's window and region, every building as a
mesh with its colours, and every tree. Next to it, `ground_<frame>.npz` holds the frame's piece of the terrain and the
ground-class grid that is draped over it. The job folder is self-contained, so it can be copied to a rented GPU as is.

A frame's region is what can show up in it or throw a shadow into it: the ground under the frame's window between the
lowest ground and the tallest roof, grown by the longest shadow the sun casts. Each frame gets only its region, because
a whole-city scene costs tens of gigabytes per Blender process.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from qipu_map.classes import CLASS_COLOURS
from qipu_map.geo.boxes import WorldBox
from qipu_map.geo.camera import Canvas
from qipu_map.model import Raster, Scene, TreeForm
from qipu_map.render.frames import Frame, FramePlan, plan_to_json
from qipu_map.render.ground import GroundShapes, ground_shapes, rasterise_ground
from qipu_map.render.look import GROUND, Light, building_look
from qipu_map.render.meshes import Mesher

JOB_FORMAT = "qipu-render-job/1"
JOB_FILE = "job.json"
TOWER_M = 35.0
_DEM_MARGIN_M = 20.0
_GROUND_MARGIN_M = 10.0
_DIGITS = 3


@dataclass(frozen=True)
class CyclesSettings:
    """Cycles settings. 16 samples with the OptiX denoiser is what the published city tiles were rendered with."""

    samples: int = 16
    device: str = "OPTIX"
    filter_width: float = 1.0
    max_bounces: int = 8


def window_ground_box(canvas: Canvas, frame: Frame, z_low: float, z_high: float) -> WorldBox:
    """The world box of all points between heights `z_low` and `z_high` that land inside the frame's window."""
    m, cam = canvas.camera.metres_per_px, canvas.camera
    xs, ys = [], []
    for u in (frame.x, frame.x + frame.w):
        for v in (frame.y, frame.y + frame.h):
            for z in (z_low, z_high):
                x, y = cam.ground_from_screen(canvas.left + u * m, canvas.top - v * m, z)
                xs.append(x)
                ys.append(y)
    return WorldBox(min(xs), min(ys), max(xs), max(ys))


def _round(values: Any) -> list[Any]:
    out: list[Any] = np.round(np.asarray(values, dtype=np.float64), _DIGITS).tolist()
    return out


def _buildings(scene: Scene, mesher: Mesher) -> tuple[list[dict[str, Any]], list[WorldBox]]:
    out, boxes = [], []
    for index, b in enumerate(scene.buildings):
        if not b.stands_in(scene.year):
            continue
        mesh, look = mesher(b), building_look(b)
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        out.append(
            {
                "index": index,
                "ground": round(b.ground_m, _DIGITS),
                "tower": b.height_m > TOWER_M,
                "wall": list(look.wall),
                "roof": list(look.roof),
                "glass": list(look.glass),
                "vertices": _round(verts),
                "faces": [list(f) for f in mesh.faces],
                "classes": [int(c) for c in mesh.face_class],
            }
        )
        boxes.append(
            WorldBox(
                float(np.min(verts[:, 0])),
                float(np.min(verts[:, 1])),
                float(np.max(verts[:, 0])),
                float(np.max(verts[:, 1])),
            )
        )
    return out, boxes


def _trees(scene: Scene, terrain: Raster) -> list[dict[str, Any]]:
    trees = [t for t in scene.trees if t.year_planted is None or t.year_planted <= scene.year]
    if not trees:
        return []
    z = terrain.sample([t.x for t in trees], [t.y for t in trees])
    return [
        {
            "x": round(t.x, _DIGITS),
            "y": round(t.y, _DIGITS),
            "z": round(float(g), _DIGITS),
            "height": t.height_m,
            "crown": t.crown_m,
            "conifer": t.form == TreeForm.CONIFER,
        }
        for t, g in zip(trees, z, strict=True)
    ]


@dataclass(frozen=True)
class JobInputs:
    scene: Scene
    plan: FramePlan
    terrain: Raster
    mesher: Mesher
    light: Light
    cycles: CyclesSettings


def write_job(inputs: JobInputs, job_dir: Path, frames: tuple[Frame, ...] | None = None) -> Path:
    """Write `job.json` and one ground file per frame into `job_dir`. Outputs go to the job folder's parent."""
    job_dir.mkdir(parents=True, exist_ok=True)
    scene, plan, terrain = inputs.scene, inputs.plan, inputs.terrain
    buildings, boxes = _buildings(scene, inputs.mesher)
    tallest = max([b.ground_m + b.height_m for b in scene.buildings] + [float(np.max(terrain.data)), 0.0])
    lowest = float(np.min(terrain.data))
    shadow = tallest / math.tan(math.radians(inputs.light.sun_elevation_deg))
    shapes = ground_shapes(scene)
    frame_specs = []
    for frame in frames if frames is not None else plan.frames:
        region = window_ground_box(plan.canvas, frame, min(lowest, 0.0), tallest).grown(shadow + _DEM_MARGIN_M)
        textured = window_ground_box(plan.canvas, frame, lowest, float(np.max(terrain.data))).grown(_GROUND_MARGIN_M)
        ground_file = f"ground_{frame.name}.npz"
        _write_ground(job_dir / ground_file, terrain.crop(region), shapes, textured, plan.canvas.camera.metres_per_px)
        frame_specs.append(
            {
                **asdict(frame),
                "region": _round(region),
                "ground": ground_file,
                "buildings": [i for i, box in enumerate(boxes) if box.intersects(region)],
            }
        )
    job = {
        "format": JOB_FORMAT,
        "out_dir": "..",
        "canvas": plan_to_json(plan, scene.year)["canvas"],
        "light": asdict(inputs.light),
        "cycles": asdict(inputs.cycles),
        "tower_m": TOWER_M,
        "class_colours": {str(int(c)): list(rgb) for c, rgb in CLASS_COLOURS.items()},
        "ground_colours": {str(int(c)): list(rgb) for c, rgb in GROUND.items()},
        "frames": frame_specs,
        "buildings": buildings,
        "trees": _trees(scene, terrain),
    }
    path = job_dir / JOB_FILE
    path.write_text(json.dumps(job, separators=(",", ":"), sort_keys=True))
    return path


def _write_ground(path: Path, dem: Raster, shapes: GroundShapes, box: WorldBox, cell: float) -> None:
    grid = rasterise_ground(shapes, box, cell)
    np.savez_compressed(
        path,
        dem=dem.data.astype(np.float32),
        dem_origin=np.array([dem.x0, dem.y0, dem.cell]),
        classes=grid.classes,
        classes_origin=np.array([grid.x0, grid.y0, grid.cell]),
    )
