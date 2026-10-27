from pathlib import Path

import numpy as np
import pytest

from qipu_map.geo.camera import Canvas
from qipu_map.render.frames import plan_frames, save_plan
from qipu_map.render.mosaic import load_canvas
from qipu_map.render.passes import encode_ids, pass_path, write_png

from .scenes import CAMERA


def cut(full: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """A frame's window of the canvas, padded with noise where it runs past the edge."""
    out = np.full((h, w, *full.shape[2:]), 77, dtype=full.dtype)
    part = full[y : y + h, x : x + w]
    out[: part.shape[0], : part.shape[1]] = part
    return out


def test_mosaic_round_trip_for_every_pass(tmp_path: Path) -> None:
    w, h = 300, 220
    plan = plan_frames(Canvas(CAMERA, 0.0, 0.0, w, h), 128, 96, 16)
    rng = np.random.default_rng(1)
    beauty = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    classes = rng.integers(0, 11, (h, w), dtype=np.uint8)
    ids = rng.integers(0, 1 << 24, (h, w), dtype=np.uint32)
    for f in plan.frames:
        # Each frame's overlap gets its own noise, so only owned pixels can survive the round trip.
        noisy = rng.integers(0, 256, (f.h, f.w, 3), dtype=np.uint8)
        b = cut(beauty, f.x, f.y, f.w, f.h)
        x0, y0, x1, y1 = plan.owned(f)
        keep = np.zeros((f.h, f.w), dtype=bool)
        keep[y0 - f.y : y1 - f.y, x0 - f.x : x1 - f.x] = True
        write_png(pass_path(tmp_path, f.name, "beauty"), np.where(keep[..., None], b, noisy))
        write_png(pass_path(tmp_path, f.name, "class"), cut(classes, f.x, f.y, f.w, f.h))
        write_png(pass_path(tmp_path, f.name, "id"), encode_ids(cut(ids, f.x, f.y, f.w, f.h)))
    save_plan(plan, 2026, tmp_path)
    assert (load_canvas(tmp_path, "beauty") == beauty).all()
    assert (load_canvas(tmp_path, "class") == classes).all()
    got = load_canvas(tmp_path, "id")
    assert got.dtype == np.uint32
    assert (got == ids).all()


def test_a_frame_of_the_wrong_size_is_refused(tmp_path: Path) -> None:
    plan = plan_frames(Canvas(CAMERA, 0.0, 0.0, 50, 40), 64, 48, 8)
    save_plan(plan, 2026, tmp_path)
    write_png(pass_path(tmp_path, plan.frames[0].name, "class"), np.zeros((10, 10), dtype=np.uint8))
    with pytest.raises(ValueError, match="expected 64x48"):
        load_canvas(tmp_path, "class")
