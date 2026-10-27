"""The `qipu-map ingest` command: fetch the open data for an area, then normalise it into the stage's layers."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from qipu_map.cache import is_fresh, mark_done, stage_key
from qipu_map.context import Context, add_common, context_from_args
from qipu_map.ingest.fetch import fetch_all
from qipu_map.ingest.grid import LocalGrid
from qipu_map.ingest.http import UrllibHttp
from qipu_map.ingest.normalise import IngestArea, normalise
from qipu_map.ingest.raw import RawStore
from qipu_map.ingest.sources import sources_for

log = logging.getLogger(__name__)

DEFAULT_MARGIN_M = 60.0


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser("ingest", help="fetch and normalise the open data for an area")
    add_common(parser)
    parser.add_argument(
        "--raw", type=Path, default=None, help="use this raw folder as it is, with no network (CI, the sample)"
    )
    parser.add_argument(
        "--margin", type=float, default=DEFAULT_MARGIN_M, help="metres fetched around the area (default 60)"
    )
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    ctx = context_from_args(args)
    counts = ingest(ctx, args.raw, args.margin)
    log.info(
        "ingest %s/%s: %s", ctx.city.id, ctx.area, ", ".join(f"{k} {v}" for k, v in counts.items()) or "up to date"
    )
    return 0


def area_of(ctx: Context, margin_m: float) -> IngestArea:
    p = ctx.projection
    return IngestArea(
        geo=ctx.bbox.grown(margin_m, p),
        box=ctx.box,
        margin_m=margin_m,
        scale=(p.kx, p.ky),
        survey_year=ctx.city.eras.footprint_survey_year,
    )


def ingest(ctx: Context, raw_dir: Path | None, margin_m: float) -> dict[str, int]:
    """Fetch (unless `raw_dir` is given) and normalise into the work folder's ingest/. Skipped when nothing changed."""
    out = ctx.work.ingest
    sources = sources_for(ctx.city.sources)
    area = area_of(ctx, margin_m)
    store = RawStore(raw_dir if raw_dir is not None else out / "raw")
    if raw_dir is None:
        grid = LocalGrid.covering(area.box, margin_m)
        fetch_all(store, sources=sources, box=area.geo, grid=grid, projection=ctx.projection, http=UrllibHttp())
    params = {"area": ctx.bbox, "margin_m": margin_m, "survey_year": area.survey_year, "sources": sorted(sources)}
    key = stage_key("ingest", [p for p in store.root.iterdir() if p.is_file()], params)
    if is_fresh(out, key):
        return {}
    counts = normalise(store, sources, area, out)
    mark_done(out, key)
    return counts
