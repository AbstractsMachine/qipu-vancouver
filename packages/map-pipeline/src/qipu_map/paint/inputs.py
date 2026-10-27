"""Read what the render stage left: the beauty and class canvases, and where the canvas sits in the world.

The canvas's top-left corner in world pixels (`Canvas.world_px`) fixes the paint grid to the world: every canvas sits on
whole pixels of the screen plane, so two areas share their tiles' positions and seeds exactly.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from qipu_map.paint.run import Inputs
from qipu_map.render.frames import load_plan
from qipu_map.render.mosaic import load_canvas


def load_inputs(render_dir: Path) -> Inputs:
    """Read a render folder's beauty and class canvases and the canvas's top-left in world pixels."""
    beauty = np.asarray(load_canvas(render_dir, "beauty"), dtype=np.uint8)
    classes = np.asarray(load_canvas(render_dir, "class"), dtype=np.uint8)
    origin = load_plan(render_dir).canvas.world_px
    return Inputs(np.ascontiguousarray(beauty), np.ascontiguousarray(classes), origin)
