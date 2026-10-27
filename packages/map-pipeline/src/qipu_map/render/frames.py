"""Cut the canvas into frames a renderer can draw one at a time.

The canvas of a city is far too big for one render (Vancouver at 25 cm a pixel is about 80 000 pixels wide), so the
renderer draws fixed-size frames and the mosaic puts them back together. Neighbouring frames overlap by a margin: the
denoiser and the pixel filter see a little past a frame's edge, so the seam is taken from the middle of the overlap,
where both frames have full context. Frames on the right and bottom edges may run past the canvas; the mosaic crops
them.

`frames.json` holds the canvas (so a reader can rebuild `geo.camera.Canvas` without the scene) and each frame's window
in canvas pixels.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from qipu_map.geo.camera import Canvas, ObliqueCamera

FRAMES_FORMAT = "qipu-frames/1"
FRAMES_FILE = "frames.json"


@dataclass(frozen=True)
class Frame:
    """A window of the canvas, in canvas pixels: x right, y down, (x, y) its top-left pixel."""

    name: str
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class FramePlan:
    """The canvas and the overlapping frames that cover it, with their size and overlap in pixels."""

    canvas: Canvas
    frames: tuple[Frame, ...]
    frame_w: int
    frame_h: int
    overlap_px: int

    def owned(self, frame: Frame) -> tuple[int, int, int, int]:
        """The part of the canvas (x0, y0, x1, y1) this frame supplies to the mosaic: its window minus half the overlap
        on every side that has a neighbour, clipped to the canvas. The owned parts of all frames tile the canvas."""
        # A frame has a neighbour on the right exactly when it ends inside the canvas (see `_starts`); same downwards.
        half, rest = self.overlap_px // 2, self.overlap_px - self.overlap_px // 2
        width, height = self.canvas.width, self.canvas.height
        x0 = frame.x + half if frame.x > 0 else 0
        y0 = frame.y + half if frame.y > 0 else 0
        x1 = frame.x + frame.w - rest if frame.x + frame.w < width else width
        y1 = frame.y + frame.h - rest if frame.y + frame.h < height else height
        return (x0, y0, x1, y1)


def frame_name(col: int, row: int) -> str:
    return f"c{col:03d}_r{row:03d}"


def _starts(length: int, size: int, overlap: int) -> list[int]:
    if length <= size:
        return [0]
    step = size - overlap
    n = math.ceil((length - overlap) / step)
    return [i * step for i in range(n)]


def plan_frames(canvas: Canvas, frame_w: int = 2048, frame_h: int = 1536, overlap_px: int = 64) -> FramePlan:
    """Frames of `frame_w` x `frame_h` pixels that cover the canvas, overlapping by `overlap_px`, in row-major order."""
    if not 0 <= overlap_px < min(frame_w, frame_h) // 2:
        raise ValueError(f"overlap_px must be in [0, {min(frame_w, frame_h) // 2}), got {overlap_px}")
    frames = tuple(
        Frame(frame_name(col, row), x, y, frame_w, frame_h)
        for row, y in enumerate(_starts(canvas.height, frame_h, overlap_px))
        for col, x in enumerate(_starts(canvas.width, frame_w, overlap_px))
    )
    return FramePlan(canvas, frames, frame_w, frame_h, overlap_px)


def plan_to_json(plan: FramePlan, year: int) -> dict[str, Any]:
    """The frame plan as a JSON-ready dict for `year`, in the `qipu-frames/1` format."""
    c = plan.canvas
    return {
        "format": FRAMES_FORMAT,
        "year": year,
        "canvas": {
            "left": c.left,
            "top": c.top,
            "width": c.width,
            "height": c.height,
            "metres_per_px": c.camera.metres_per_px,
            "azimuth_deg": c.camera.azimuth_deg,
            "elevation_deg": c.camera.elevation_deg,
        },
        "frame_w": plan.frame_w,
        "frame_h": plan.frame_h,
        "overlap_px": plan.overlap_px,
        "frames": [asdict(f) for f in plan.frames],
    }


def plan_from_json(d: dict[str, Any]) -> FramePlan:
    if d.get("format") != FRAMES_FORMAT:
        raise ValueError(f"not a {FRAMES_FORMAT} file (format={d.get('format')!r})")
    c = d["canvas"]
    camera = ObliqueCamera(c["azimuth_deg"], c["elevation_deg"], c["metres_per_px"])
    canvas = Canvas(camera, c["left"], c["top"], c["width"], c["height"])
    frames = tuple(Frame(f["name"], f["x"], f["y"], f["w"], f["h"]) for f in d["frames"])
    return FramePlan(canvas, frames, d["frame_w"], d["frame_h"], d["overlap_px"])


def save_plan(plan: FramePlan, year: int, out_dir: Path) -> Path:
    """Write the plan to `frames.json` in `out_dir` and return its path. The render stage writes it last."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FRAMES_FILE
    path.write_text(json.dumps(plan_to_json(plan, year), indent=1, sort_keys=True) + "\n")
    return path


def load_plan(render_dir: Path) -> FramePlan:
    """Read the frame plan from the render folder's `frames.json`."""
    return plan_from_json(json.loads((render_dir / FRAMES_FILE).read_text()))
