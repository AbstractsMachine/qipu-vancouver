"""The `qipu-map tiles` command: cut every pyramid of a release.

Today's painted canvas (paint/<today>/canvas.png), each past year's layer (eras/<year>/layer.png) and each segment's
date map (eras/switch/<a>-<b>/dates.png). Pyramids of years or segments that no longer exist are removed.
"""

from __future__ import annotations

import argparse
import shutil
from typing import Any

from qipu_map.context import Context, add_common, context_from_args
from qipu_map.eras.build import segments
from qipu_map.errors import StageError
from qipu_map.imageio import image_size
from qipu_map.tiles.canvas import TileJob, tile_job


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser(
        "tiles", help="cut the painted canvas, the era layers and date maps"
    )
    add_common(parser)
    parser.add_argument("--force", action="store_true", help="rewrite pyramids whose source has not changed")
    parser.set_defaults(run=run)


def jobs(ctx: Context) -> list[TileJob]:
    """Today, then each past year's layer and each segment's date map that the eras stage wrote, oldest first."""
    work, today = ctx.work, ctx.city.eras.today
    found = [TileJob("today", work.canvas(today), work.today_tiles())]
    found += [
        TileJob(f"year {y}", work.layer(y), work.year_tiles(y)) for y in ctx.city.eras.years if work.layer(y).is_file()
    ]
    found += [
        TileJob(f"switch {a}-{b}", work.dates(a, b), work.switch_tiles(a, b), dates=True)
        for a, b in segments(ctx.city.eras.years, today)
        if work.dates(a, b).is_file()
    ]
    return found


def _remove_unlisted(ctx: Context, listed: list[TileJob]) -> None:
    keep = {j.out_dir for j in listed}
    for folder in ("years", "switch"):
        for d in sorted((ctx.work.tiles / folder).glob("*")):
            if d.is_dir() and d not in keep:
                shutil.rmtree(d)


def run(args: argparse.Namespace) -> int:
    ctx = context_from_args(args)
    tile_size = ctx.city.camera.tile_size
    today, *past = jobs(ctx)
    if not today.source.is_file():
        raise StageError(f"no painted canvas at {today.source}: run `qipu-map paint` first")
    today_size = image_size(today.source)
    tile_job(today, tile_size=tile_size, force=args.force)
    for job in past:
        tile_job(job, tile_size=tile_size, today_size=today_size, force=args.force)
    _remove_unlisted(ctx, past)
    return 0
