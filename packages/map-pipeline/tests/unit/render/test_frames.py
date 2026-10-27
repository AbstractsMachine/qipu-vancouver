from pathlib import Path

import numpy as np
import pytest

from qipu_map.geo.camera import Canvas
from qipu_map.render.frames import load_plan, plan_frames, save_plan

from .scenes import CAMERA


def canvas(w: int, h: int) -> Canvas:
    return Canvas(CAMERA, -10.0, 50.0, w, h)


def test_frames_cover_the_canvas_with_the_overlap() -> None:
    plan = plan_frames(canvas(5000, 3000), 2048, 1536, 64)
    xs = sorted({f.x for f in plan.frames})
    ys = sorted({f.y for f in plan.frames})
    assert xs == [0, 1984, 3968]
    assert ys == [0, 1472]
    assert all(f.w == 2048 and f.h == 1536 for f in plan.frames)
    assert max(f.x + f.w for f in plan.frames) >= 5000
    assert max(f.y + f.h for f in plan.frames) >= 3000


def test_frames_are_named_by_column_and_row_in_row_major_order() -> None:
    plan = plan_frames(canvas(3000, 2000), 2048, 1536, 64)
    assert [f.name for f in plan.frames] == ["c000_r000", "c001_r000", "c000_r001", "c001_r001"]


def test_a_small_canvas_is_one_frame() -> None:
    plan = plan_frames(canvas(300, 200), 2048, 1536, 64)
    assert len(plan.frames) == 1
    assert plan.owned(plan.frames[0]) == (0, 0, 300, 200)


@pytest.mark.parametrize(("w", "h", "overlap"), [(5000, 3000, 64), (4096, 1536, 0), (2049, 1537, 63), (777, 4000, 10)])
def test_owned_parts_tile_the_canvas_exactly_once(w: int, h: int, overlap: int) -> None:
    plan = plan_frames(canvas(w, h), 2048, 1536, overlap)
    count = np.zeros((h, w), dtype=np.int32)
    for f in plan.frames:
        x0, y0, x1, y1 = plan.owned(f)
        assert f.x <= x0
        assert f.y <= y0
        assert x1 <= f.x + f.w
        assert y1 <= f.y + f.h
        count[y0:y1, x0:x1] += 1
    assert (count == 1).all()


def test_seams_sit_in_the_middle_of_the_overlap() -> None:
    plan = plan_frames(canvas(5000, 1000), 2048, 1536, 64)
    first, second = plan.frames[0], plan.frames[1]
    assert plan.owned(first)[2] == plan.owned(second)[0] == second.x + 32


def test_overlap_must_be_less_than_half_a_frame() -> None:
    with pytest.raises(ValueError, match="overlap_px"):
        plan_frames(canvas(100, 100), 64, 64, 32)


def test_plan_round_trips_through_frames_json(tmp_path: Path) -> None:
    plan = plan_frames(canvas(3000, 2000), 1024, 768, 32)
    save_plan(plan, 1972, tmp_path)
    again = load_plan(tmp_path)
    assert again == plan
    text = (tmp_path / "frames.json").read_text()
    assert '"metres_per_px": 0.5' in text
    assert '"year": 1972' in text


def test_frames_json_must_have_its_format(tmp_path: Path) -> None:
    (tmp_path / "frames.json").write_text('{"format": "something-else"}')
    with pytest.raises(ValueError, match="qipu-frames/1"):
        load_plan(tmp_path)
