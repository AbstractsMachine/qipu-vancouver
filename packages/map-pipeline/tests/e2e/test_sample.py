"""`qipu-map sample` end to end: the bundled West End sample through every stage, with the CPU stand-ins for Blender
and the AI model, to a release a viewer can open."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qipu_map.cli import main


@pytest.mark.e2e
def test_the_sample_publishes_a_complete_release(tmp_path: Path) -> None:
    assert main(["sample", "--work", str(tmp_path)]) == 0
    root = tmp_path / "release" / "sample"
    manifest = json.loads((root / "manifest.json").read_text())
    assert [y["year"] for y in manifest["years"]] == [1930, 1950, 1972, 1982]
    assert [(s["from"], s["to"]) for s in manifest["switch"]] == [
        (1930, 1950),
        (1950, 1972),
        (1972, 1982),
        (1982, 2026),
    ]
    for layer in [manifest["today"], *manifest["years"], *manifest["switch"]]:
        z = str(layer["zmax"])
        have = layer["have"][z]
        first = root / layer["path"].format(z=z, x=have["x0"], y=have["y0"])
        assert first.is_file() or have["cols"] * have["rows"] > 1
    assert len(list(root.rglob("*.webp"))) > 100
