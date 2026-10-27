"""Skip a stage when nothing it depends on has changed.

A stage computes a key from the bytes of its inputs, its parameters and the package version, and writes the key to
`.stamp` in its output folder when it finishes. If the stamp matches the next time, the stage does nothing. A stage
that fails leaves no stamp, so a re-run starts it again.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from qipu_map import __version__
from qipu_map.hashing import file_digest, value_digest

STAMP = ".stamp"


def stage_key(stage: str, inputs: Iterable[Path], params: Any) -> str:
    """Inputs are named by their path relative to the folder they share, so two files with the same name (each year's
    scene.json) both count."""
    files = sorted(Path(p) for p in inputs)
    root = Path(os.path.commonpath(files)) if len(files) > 1 else None
    return value_digest(
        {
            "stage": stage,
            "version": __version__,
            "inputs": {_label(p, root): file_digest(p) for p in files},
            "params": params,
        }
    )


def is_fresh(out_dir: Path, key: str) -> bool:
    stamp = out_dir / STAMP
    return stamp.is_file() and stamp.read_text().strip() == key


def mark_done(out_dir: Path, key: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / STAMP).write_text(key + "\n")


def _label(path: Path, root: Path | None) -> str:
    return path.name if root is None or root == path else path.relative_to(root).as_posix()
