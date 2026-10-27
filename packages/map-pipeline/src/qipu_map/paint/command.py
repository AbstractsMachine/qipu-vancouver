"""The `qipu-map paint` command.

    qipu-map paint --backend identity|diffusers|replay [--year Y] [--max-tiles N] [--colour-restore] [--replay-dir D]
    [--force]

Writes `paint/<year>/canvas.png` (RGBA: transparent where the render shows nothing), the tile cache
`paint/<year>/tiles/` and `paint/<year>/report.json`. The stage is skipped when the render, the recipe, the prompts and
the options are unchanged since the last finished run; `--force` runs it anyway, and the tile cache still spares the
tiles whose inputs did not change.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qipu_map import cache
from qipu_map.context import add_common, context_from_args
from qipu_map.errors import StageError
from qipu_map.files import write_json
from qipu_map.imageio import write_png
from qipu_map.paint.backends import make_painter
from qipu_map.paint.inputs import load_inputs
from qipu_map.paint.prompts import PromptSet
from qipu_map.paint.run import Options, paint_canvas, with_coverage
from qipu_map.paint.tilecache import TileCache
from qipu_map.render.frames import FRAMES_FILE, load_plan
from qipu_map.render.passes import pass_path

log = logging.getLogger(__name__)
STAGE = "paint"
# Bump when the painting rules change, so every cached canvas is painted again (unchanged tiles still come from the
# tile cache).
VERSION = 1


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser("paint", help="paint the render into the map's photographic skin")
    add_common(parser)
    parser.add_argument("--backend", choices=("identity", "diffusers", "replay"), default="identity")
    parser.add_argument("--year", type=int, default=None, help="the year to paint (default: today)")
    parser.add_argument("--max-tiles", type=int, default=None, help="paint at most N tiles; the rest keep the render")
    parser.add_argument(
        "--colour-restore", action="store_true", help="pull global contrast and saturation to the render's"
    )
    parser.add_argument("--replay-dir", type=Path, default=None, help="recorded tiles for --backend replay")
    parser.add_argument("--force", action="store_true", help="paint even when nothing has changed since the last run")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    ctx = context_from_args(args)
    city = ctx.city
    year = args.year if args.year is not None else city.eras.today
    others = [ctx.work.paint_tiles(y) for y in (city.eras.today, *city.eras.years) if y != year]
    if not ctx.work.frames(year).is_file():
        raise StageError(f"no render at {ctx.work.render(year)}: run `qipu-map render --year {year}` first")
    out = ctx.work.paint(year)
    prompts = PromptSet.load(city.id.rsplit("/", 1)[-1])
    options = Options(year=year, today=city.eras.today, max_tiles=args.max_tiles, colour_restore=args.colour_restore)
    params = {
        "version": VERSION,
        "backend": args.backend,
        "replay_dir": str(args.replay_dir) if args.replay_dir else None,
        "recipe": asdict(city.paint),
        "prompts": asdict(prompts),
        "options": asdict(options),
    }
    key = cache.stage_key(STAGE, render_files(ctx.work.render(year)), params)
    if not args.force and cache.is_fresh(out, key):
        log.info("paint %s: up to date", year)
        return 0

    inputs = load_inputs(ctx.work.render(year))
    painter = make_painter(args.backend, city.paint.model, city.paint.steps, city.paint.guidance, args.replay_dir)
    canvas, report = paint_canvas(
        inputs,
        city.paint,
        painter,
        prompts=prompts,
        cache=TileCache(ctx.work.paint_tiles(year), also=[d for d in others if d.is_dir()]),
        options=options,
    )
    write_png(ctx.work.canvas(year), with_coverage(canvas, inputs.classes))
    write_json(ctx.work.paint_report(year), report.as_json())
    cache.mark_done(out, key)
    log.info(
        "%s %d: %d tiles painted, %d reused, %d re-rolled, %d water, %.0f s",
        city.id,
        year,
        report.painted,
        report.reused,
        report.rerolled,
        report.water_tiles,
        report.seconds,
    )
    return 0


def render_files(render_dir: Path) -> list[Path]:
    """What the painting is made from: the frame plan and each frame's beauty and class passes."""
    frames = [f.name for f in load_plan(render_dir).frames]
    passes = [pass_path(render_dir, name, kind) for name in frames for kind in ("beauty", "class")]
    return [render_dir / FRAMES_FILE, *passes]
