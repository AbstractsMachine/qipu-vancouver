"""The `qipu-map sample` command: every stage, in order, on the West End sample that ships with the repository.

By default it uses the stand-ins for the GPU stages (the preview renderer and the identity painter), so it runs on any
machine in about a minute. With `--render-backend blender --paint-backend diffusers` it is the real chain.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from qipu_map.cli import main
from qipu_map.config import load_city

# The sample sits in the repository's examples/, next to the other packages' Vancouver samples.
SAMPLE_RAW = Path(__file__).resolve().parents[4] / "examples" / "vancouver" / "west-end"
CITY, AREA, RELEASE = "vancouver", "west-end", "sample"

log = logging.getLogger(__name__)


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser("sample", help="run every stage on the bundled West End sample")
    parser.add_argument("--work", type=Path, default=Path("build/sample"), help="work folder (default build/sample)")
    parser.add_argument("--raw", type=Path, default=SAMPLE_RAW, help="the sample's raw open data")
    parser.add_argument("--render-backend", choices=("preview", "blender"), default="preview")
    parser.add_argument("--paint-backend", choices=("identity", "diffusers"), default="identity")
    parser.set_defaults(run=run)


def steps(work: Path, raw: Path, render_backend: str, paint_backend: str) -> list[list[str]]:
    eras = load_city(CITY).eras
    where = ["--city", CITY, "--area", AREA, "--work", str(work)]
    chain = [
        ["ingest", *where, "--raw", str(raw)],
        ["scene", *where],
        ["eras", "scene", *where],
        ["render", *where, "--backend", render_backend],
    ]
    chain += [["paint", *where, "--backend", paint_backend, "--year", str(y)] for y in (eras.today, *eras.years)]
    chain += [
        ["eras", "layers", *where],
        ["tiles", *where],
        ["publish", *where, "--release", RELEASE, "--to", str(work / "release")],
    ]
    return chain


def run(args: argparse.Namespace) -> int:
    for argv in steps(args.work, args.raw, args.render_backend, args.paint_backend):
        log.info("qipu-map %s", " ".join(argv))
        if (code := main(argv)) != 0:
            return code
    log.info("done: the release is in %s", args.work / "release" / RELEASE)
    return 0
