import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from qipu_map.classes import CLASS_COLOURS, SurfaceClass
from qipu_map.render import blender_backend as bb
from qipu_map.render.passes import pass_path, read_png, write_png


def test_command_runs_the_build_script_on_one_frame() -> None:
    cmd = bb.blender_command("blender", Path("w/job/job.json"), "c000_r001")
    assert cmd[0] == "blender"
    assert "--background" in cmd
    assert "--factory-startup" in cmd
    assert cmd[cmd.index("--python") + 1].endswith("render/blender/build.py")
    assert cmd[-3:] == ["--", "w/job/job.json", "c000_r001"]
    assert Path(cmd[cmd.index("--python") + 1]).is_file()


def test_blender_comes_from_the_environment_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLENDER", "/opt/blender/blender")
    assert bb.find_blender() == "/opt/blender/blender"


def test_blender_missing_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLENDER", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr(bb, "_MACOS_APP", Path("/nowhere/Blender"))
    with pytest.raises(FileNotFoundError, match="BLENDER"):
        bb.find_blender()


class FakeBlender:
    """Writes what build.py writes: a beauty, a class pass in flat colours and an id pass."""

    def __init__(self, out_dir: Path, write: bool = True, code: int = 0) -> None:
        self.out_dir, self.write, self.code = out_dir, write, code
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        name = cmd[-1]
        if self.write:
            rgb = np.zeros((4, 6, 3), dtype=np.uint8)
            rgb[:, :3] = CLASS_COLOURS[SurfaceClass.ROOF]
            rgb[:, 3:] = CLASS_COLOURS[SurfaceClass.WATER]
            write_png(self.out_dir / f"{name}.classrgb.png", rgb)
            write_png(pass_path(self.out_dir, name, "beauty"), rgb)
            write_png(pass_path(self.out_dir, name, "id"), rgb)
        return subprocess.CompletedProcess(cmd, self.code, "out", "err")


def job_file(tmp_path: Path) -> Path:
    job = tmp_path / "render" / "job" / "job.json"
    job.parent.mkdir(parents=True)
    job.write_text("{}")
    return job


def test_frames_are_rendered_and_class_colours_become_ids(tmp_path: Path) -> None:
    job = job_file(tmp_path)
    fake = FakeBlender(job.parent.parent)
    bb.render_frames(job, ["a", "b"], blender="blender", run=fake)
    assert [c[-1] for c in fake.calls] == ["a", "b"]
    classes = read_png(pass_path(job.parent.parent, "a", "class"))
    assert classes[0].tolist() == [7, 7, 7, 4, 4, 4]
    assert not (job.parent.parent / "a.classrgb.png").exists()
    assert (job.parent / "a.log").read_text() == "outerr"


def test_finished_frames_are_skipped(tmp_path: Path) -> None:
    job = job_file(tmp_path)
    fake = FakeBlender(job.parent.parent)
    bb.render_frames(job, ["a"], blender="blender", run=fake)
    bb.render_frames(job, ["a"], blender="blender", run=fake)
    assert len(fake.calls) == 1


def test_frames_of_an_older_job_are_rendered_again(tmp_path: Path) -> None:
    job = job_file(tmp_path)
    fake = FakeBlender(job.parent.parent)
    bb.render_frames(job, ["a"], blender="blender", run=fake)
    job.write_text('{"light": "changed"}')
    bb.render_frames(job, ["a"], blender="blender", run=fake)
    assert len(fake.calls) == 2


def test_passes_without_a_marker_are_not_trusted(tmp_path: Path) -> None:
    job = job_file(tmp_path)
    fake = FakeBlender(job.parent.parent)
    bb.render_frames(job, ["a"], blender="blender", run=fake)
    bb.done_marker(job, "a").unlink()
    bb.render_frames(job, ["a"], blender="blender", run=fake)
    assert len(fake.calls) == 2


def test_a_failed_frame_stops_the_run(tmp_path: Path) -> None:
    job = job_file(tmp_path)
    with pytest.raises(RuntimeError, match="exit 1"):
        bb.render_frames(job, ["a"], blender="blender", run=FakeBlender(job.parent.parent, code=1))


def test_a_clean_exit_without_files_is_a_failure(tmp_path: Path) -> None:
    job = job_file(tmp_path)
    with pytest.raises(RuntimeError, match="wrote no beauty, id pass"):
        bb.render_frames(job, ["a"], blender="blender", run=FakeBlender(job.parent.parent, write=False))
