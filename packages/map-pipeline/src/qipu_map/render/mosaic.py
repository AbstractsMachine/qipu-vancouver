"""Put a pass of the render back together into the whole canvas.

Each frame supplies the part of the canvas it owns (`FramePlan.owned`), so every canvas pixel comes from exactly one
frame and seams sit in the middle of an overlap. The paint and era stages read the canvas through `load_canvas`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from qipu_map.render.frames import load_plan
from qipu_map.render.passes import Kind, decode_ids, pass_path, read_png


def load_canvas(render_dir: Path, kind: Kind) -> NDArray[np.generic]:
    """The whole canvas of one pass: beauty as (h, w, 3) uint8, class as (h, w) uint8 class ids, id as (h, w) uint32
    building ids (1 + index in `scene.buildings`, 0 for none)."""
    plan = load_plan(render_dir)
    w, h = plan.canvas.width, plan.canvas.height
    canvas: NDArray[np.generic]
    if kind == "beauty":
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
    elif kind == "class":
        canvas = np.zeros((h, w), dtype=np.uint8)
    else:
        canvas = np.zeros((h, w), dtype=np.uint32)
    for frame in plan.frames:
        img: NDArray[np.generic] = read_png(pass_path(render_dir, frame.name, kind))
        if kind == "id":
            img = decode_ids(img)
        if img.shape[:2] != (frame.h, frame.w):
            raise ValueError(f"{frame.name}.{kind}.png is {img.shape[1]}x{img.shape[0]}, expected {frame.w}x{frame.h}")
        x0, y0, x1, y1 = plan.owned(frame)
        canvas[y0:y1, x0:x1] = img[y0 - frame.y : y1 - frame.y, x0 - frame.x : x1 - frame.x]
    return canvas
