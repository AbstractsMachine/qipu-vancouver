"""The `qipu-map publish` command: write manifest.json and ground.json, then upload the release."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any

from qipu_map.context import Context, add_common, context_from_args
from qipu_map.errors import StageError
from qipu_map.files import write_json
from qipu_map.hashing import file_digest
from qipu_map.model import Raster
from qipu_map.publish.ground import ground_grid
from qipu_map.publish.manifest import Layers, build_manifest, find_layers
from qipu_map.publish.upload import MANIFEST_KEY, THREADS, PublishError, describe, open_store, plan_upload, run_upload
from qipu_map.render.frames import load_plan

log = logging.getLogger(__name__)

GROUND_KEY = "ground.json"
_RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser("publish", help="write the manifest and upload the release")
    add_common(parser, explicit=True)
    parser.add_argument("--release", required=True, help="the release folder name, for example r20261026")
    parser.add_argument(
        "--to", required=True, help="s3://bucket/prefix, a folder, or `city` for the city file's publish.bucket_url"
    )
    parser.add_argument("--threads", type=int, default=THREADS)
    parser.add_argument("--dry-run", action="store_true", help="list what would be uploaded and stop")
    parser.set_defaults(run=run)


def write_release_files(ctx: Context, release: str) -> tuple[Layers, dict[str, Any]]:
    """Write ground.json (when the scene has terrain) and manifest.json into the tiles folder."""
    today = ctx.city.eras.today
    root = ctx.work.tiles
    layers = find_layers(root)
    if not ctx.work.frames(today).is_file():
        raise StageError(f"no frame plan at {ctx.work.frames(today)}: run `qipu-map render` first")
    canvas = load_plan(ctx.work.render(today)).canvas
    terrain = ctx.work.terrain(today)
    ground = None
    if terrain.is_file():
        write_json(root / GROUND_KEY, ground_grid(Raster.load(terrain)))
        ground = GROUND_KEY
    manifest = build_manifest(ctx.city, ctx.area, release, canvas, layers, ground=ground)
    write_json(ctx.work.manifest, manifest)
    return layers, manifest


def release_files(root: Path, layers: Layers, manifest: dict[str, Any]) -> tuple[dict[str, Path], dict[str, str]]:
    """Every object of the release (key to local file) and its MD5: the tiles the manifest names, ground, manifest."""
    digests: dict[str, str] = {}
    for layer in (layers.today, *layers.years.values(), *layers.switch.values()):
        digests.update(layer.digests)
    extra = [MANIFEST_KEY] + ([manifest["ground"]] if "ground" in manifest else [])
    digests.update({key: file_digest(root / key, "md5") for key in extra})
    return {key: root / key for key in digests}, digests


def run(args: argparse.Namespace) -> int:
    ctx = context_from_args(args)
    if not _RELEASE.match(args.release):
        raise StageError(f"release name {args.release!r}: use letters, digits, '.', '_' or '-'")
    publish = ctx.city.publish
    # Production is never a default: the city's bucket is written only when asked for by name.
    target = f"{(publish.bucket_url if args.to == 'city' else args.to).rstrip('/')}/{args.release}"
    try:
        layers, manifest = write_release_files(ctx, args.release)
        files, digests = release_files(ctx.work.tiles, layers, manifest)
        store = open_store(target, publish.endpoint_env, args.threads)
        plan = plan_upload(
            files,
            digests,
            store.md5s(),
            cache_control=publish.cache_control,
            manifest_cache_control=publish.manifest_cache_control,
        )
        log.info("%s: %d of %d objects to write, %d unchanged", target, len(plan), len(files), len(files) - len(plan))
        if args.dry_run:
            sys.stdout.write("".join(line + "\n" for line in describe(plan)))
            return 0
        run_upload(store, plan, args.threads)
    except (FileNotFoundError, ValueError, PublishError) as e:
        raise StageError(str(e)) from e
    log.info("published %s", target)
    return 0
