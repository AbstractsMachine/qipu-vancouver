"""The `qipu-map scene` command: today's scene.json and terrain.npz for an area, from its ingest folder."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from qipu_map import cache
from qipu_map.context import Context, add_common, context_from_args
from qipu_map.errors import StageError
from qipu_map.scene.inputs import FILES
from qipu_map.scene.make import SceneArea, make_scene

log = logging.getLogger(__name__)
REQUIRED = ("buildings.geojson", "dsm.npz", "dem.npz")
# Bump when the scene rules change, so every cached scene is rebuilt.
RULES_VERSION = 1


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser("scene", help="build today's 3D scene from the ingested open data")
    add_common(parser)
    parser.add_argument("--force", action="store_true", help="rebuild even when the inputs have not changed")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    return build(context_from_args(args), force=args.force)


def build(ctx: Context, *, force: bool = False) -> int:
    ingest, today = ctx.work.ingest, ctx.city.eras.today
    out = ctx.work.scene(today)
    missing = [f for f in REQUIRED if not (ingest / f).is_file()]
    if missing:
        raise StageError(f"ingest is missing {', '.join(missing)}: run `qipu-map ingest` first")
    area = SceneArea(ctx.city.id, ctx.area, today, ctx.box, ctx.projection)
    present = [ingest / f for f in FILES if (ingest / f).is_file()]
    key = cache.stage_key(
        "scene", present, {"rules": RULES_VERSION, "box": area.box, "year": today, "projection": area.projection}
    )
    if not force and cache.is_fresh(out, key):
        log.info("scene for %s %s is up to date", ctx.area, today)
        return 0
    scene, terrain = make_scene(ingest, area)
    out.mkdir(parents=True, exist_ok=True)
    terrain.save(ctx.work.terrain(today))
    scene.save(ctx.work.scene_file(today))
    cache.mark_done(out, key)
    log.info("wrote %s: %d buildings, %d trees", ctx.work.scene_file(today), len(scene.buildings), len(scene.trees))
    return 0
