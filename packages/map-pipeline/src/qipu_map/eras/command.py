"""The `qipu-map eras` command.

`qipu-map eras scene [--year Y]` derives past scenes from today's (every era year of the city file, or one).
`qipu-map eras layers`, after painting, writes each past year's eras/<year>/layer.png and every segment's
eras/switch/<a>-<b>/dates.png. `qipu-map tiles` cuts them into pyramids.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from qipu_map.context import add_common, context_from_args
from qipu_map.eras.build import write_layers_and_dates, write_past_scenes
from qipu_map.eras.rules import rules_for_city
from qipu_map.errors import StageError

log = logging.getLogger(__name__)


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser("eras", help="past years: their scenes, layers and date maps")
    steps = parser.add_subparsers(dest="eras_step", required=True)
    scene = steps.add_parser("scene", help="derive the scene of past years from today's scene")
    scene.add_argument("--year", type=int, default=None, help="one era year (default: every year in the city file)")
    layers = steps.add_parser("layers", help="build each year's layer and the date maps, after painting")
    layers.add_argument("--seed", type=int, default=0, help="seed of the dissolve noise")
    for p in (scene, layers):
        add_common(p)
        p.add_argument("--rules", type=Path, default=None, help="an era rules file (default: eras/rules/<city>.toml)")
        p.add_argument("--force", action="store_true", help="rebuild even when the inputs have not changed")
        p.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    ctx = context_from_args(args)
    rules = rules_for_city(ctx.city.id, args.rules)
    if args.eras_step == "scene":
        if args.year is not None and args.year >= ctx.city.eras.today:
            raise StageError(f"--year must be before today ({ctx.city.eras.today})")
        years = ctx.city.eras.years if args.year is None else (args.year,)
        for path in write_past_scenes(ctx, rules, years, force=args.force):
            log.info("wrote %s", path)
    else:
        for path in write_layers_and_dates(ctx, rules, seed=args.seed, force=args.force):
            log.info("wrote %s", path)
    return 0
