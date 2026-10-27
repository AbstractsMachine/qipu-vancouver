"""Writing files: atomically, and JSON in one layout.

Every JSON file the pipeline writes has sorted keys, UTF-8 text and a final newline, so the same value gives the same
bytes and a diff between two runs shows only what changed. Small files are indented one space; the big ones (a scene,
a GeoJSON layer, a render job: tens to hundreds of megabytes for a city) are compact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_atomic(path: Path, data: bytes) -> None:
    """Write through a temporary name in the same folder, so a crash never leaves a half-written file that looks
    done."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    tmp.write_bytes(data)
    tmp.replace(path)


def json_text(value: Any, *, compact: bool = False) -> str:
    """The value as JSON text in the pipeline's layout: sorted keys, UTF-8, final newline, indented one space unless
    `compact`."""
    if compact:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    return json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    """Write the value as JSON in the pipeline's layout (see `json_text`), atomically."""
    write_atomic(path, json_text(value, compact=compact).encode())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
