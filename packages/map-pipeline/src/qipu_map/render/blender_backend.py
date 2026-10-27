"""Run Blender on a job, one process per frame, and turn its flat class colours into class ids.

One process per frame keeps memory flat (a frame's scene is cut to its region) and lets frames run on as many machines
as there are. A finished frame leaves `<frame>.done` in the job folder holding the digest of the job it was rendered
from; a frame whose marker matches the current job is skipped, so a run that stopped half way picks up where it was,
and a frame rendered from an older job (a changed scene, light or camera) is rendered again.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from qipu_map.hashing import file_digest
from qipu_map.render.passes import KINDS, classes_from_rgb, pass_path, read_png, write_png

log = logging.getLogger(__name__)

BUILD_SCRIPT = Path(__file__).parent / "blender" / "build.py"
BLENDER_ENV = "BLENDER"
_MACOS_APP = Path("/Applications/Blender.app/Contents/MacOS/Blender")

Runner = Callable[..., subprocess.CompletedProcess[str]]


def find_blender() -> str:
    """$BLENDER, else `blender` on PATH, else the macOS app in its usual place."""
    if env := os.environ.get(BLENDER_ENV):
        return env
    if found := shutil.which("blender"):
        return found
    if _MACOS_APP.is_file():
        return str(_MACOS_APP)
    raise FileNotFoundError("Blender not found: install Blender 4.2 or later and put it on PATH, or set $BLENDER")


def blender_command(blender: str, job: Path, frame: str) -> list[str]:
    return [
        blender,
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(BUILD_SCRIPT),
        "--",
        str(job),
        frame,
    ]


def finish_frame(out_dir: Path, frame: str) -> None:
    """Map the flat class colours Blender wrote to class ids, and drop the colour image."""
    rgb_path = out_dir / f"{frame}.classrgb.png"
    write_png(pass_path(out_dir, frame, "class"), classes_from_rgb(read_png(rgb_path)))
    rgb_path.unlink()


def done_marker(job: Path, frame: str) -> Path:
    return job.parent / f"{frame}.done"


def frame_done(job: Path, frame: str, job_key: str) -> bool:
    """True when the frame's passes are there and were rendered from this very job."""
    marker = done_marker(job, frame)
    if not marker.is_file() or marker.read_text().strip() != job_key:
        return False
    return all(pass_path(job.parent.parent, frame, k).is_file() for k in KINDS)


def render_frames(
    job: Path,
    frames: Sequence[str],
    blender: str | None = None,
    run: Runner = subprocess.run,
    timeout_s: float = 3600.0,
) -> None:
    """Render each frame of `job` in its own Blender process. Outputs land in the job folder's parent."""
    binary = blender or find_blender()
    out_dir = job.parent.parent
    job_key = file_digest(job)
    for name in frames:
        if frame_done(job, name, job_key):
            log.info("%s: already rendered", name)
            continue
        cmd = blender_command(binary, job, name)
        log.info("%s: %s", name, " ".join(cmd))
        result = run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        (job.parent / f"{name}.log").write_text(result.stdout + result.stderr)
        if result.returncode != 0:
            raise RuntimeError(
                f"Blender failed on {name} (exit {result.returncode}); see {job.parent / (name + '.log')}"
            )
        # A zero exit is not proof: success is the output files being there (a glob that matched other files once
        # passed a failed live job as done).
        missing = [k for k in ("beauty", "id") if not pass_path(out_dir, name, k).is_file()]
        if missing or not (out_dir / f"{name}.classrgb.png").is_file():
            raise RuntimeError(f"Blender exited cleanly on {name} but wrote no {', '.join(missing) or 'class'} pass")
        finish_frame(out_dir, name)
        done_marker(job, name).write_text(job_key + "\n")
