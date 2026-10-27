"""Everything up to the paint step, on a CPU: ingest, scene, eras and the render, ready for the painter.

CI never runs Blender (the render) or FLUX.2 klein (the paint): both need a GPU. This test runs the stages in front of
the paint with the CPU stand-in for Blender and checks what the painter would be given. The painter itself is covered by
tests/unit/paint with fake painters, and `make sample-gpu` runs the real one by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

from qipu_map.cli import main
from qipu_map.sample import SAMPLE_RAW
from tests.integration.test_chain import CITY_FILE, TODAY, chain_after_ingest


def test_the_stages_before_the_paint_leave_it_what_it_needs(tmp_path: Path) -> None:
    work = tmp_path / "work"
    ingest = ["ingest", "--city", str(CITY_FILE), "--area", "corner", "--work", str(work), "--raw", str(SAMPLE_RAW)]
    before_paint = [argv for argv in chain_after_ingest(work, tmp_path / "out") if argv[0] != "paint"][:3]
    assert [argv[0] for argv in before_paint] == ["scene", "eras", "render"]
    for argv in [ingest, *before_paint]:
        assert main(argv) == 0, argv

    render = work / "ca-vancouver" / "corner" / "render" / str(TODAY)
    plan = json.loads((render / "frames.json").read_text())
    assert plan["canvas"]["width"] > 0
    assert plan["canvas"]["height"] > 0
    assert any(render.glob("*.png")), "the render passes the painter reads"
    assert not (work / "ca-vancouver" / "corner" / "paint").exists(), "nothing has been painted yet"
