"""The eras stage's two jobs, with their files. It writes only under `scene/<year>/` for past years and under `eras/`.

`write_past_scenes`, before rendering: scene/<today>/scene.json -> scene/<year>/scene.json, with today's terrain.npz.
`write_layers_and_dates`, after every year is painted: eras/<year>/layer.png for each past year, and
eras/switch/<a>-<b>/dates.png for each segment. The tiles stage cuts both into pyramids.

dates.png holds the date maps' tile encoding (R * 256 + G, B = 0; docs/tiles-format.md), so one decoder reads both.
Every output carries a cache stamp keyed on its inputs, the era rules and the seed.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterator
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from qipu_map import cache
from qipu_map.context import Context
from qipu_map.eras.compare import changed_mask, composite, shrink
from qipu_map.eras.datecodec import encode_dates, to_rgb
from qipu_map.eras.datemap import building_pixels, segment_building_dates, segment_dates
from qipu_map.eras.layer import past_layer
from qipu_map.eras.past import derive_past_scene, prepare_today
from qipu_map.eras.rules import EraRules, Evidence
from qipu_map.errors import StageError
from qipu_map.hashing import value_digest
from qipu_map.imageio import Pixels, read_image, write_png
from qipu_map.model import Raster, Scene
from qipu_map.render.frames import load_plan
from qipu_map.render.mosaic import load_canvas

log = logging.getLogger(__name__)

VERSION = 1  # bump when a rule of this stage changes, so every cached output is rebuilt


def segments(years: tuple[int, ...], today: int) -> Iterator[tuple[int, int]]:
    """Consecutive pairs of era years, the last one ending at today."""
    yield from pairwise((*years, today))


def load_evidence(ctx: Context, rules: EraRules, year: int) -> tuple[Evidence, Raster] | None:
    ev = rules.evidence_for(year)
    if ev is None:
        return None
    path = ctx.work.evidence(ev.name)
    if not path.exists():
        log.warning("no built-up mask %s for %d: stand-ins use the neighbour test only", path, year)
        return None
    return ev, Raster.load(path)


def load_today(ctx: Context, rules: EraRules) -> Scene:
    path = ctx.work.scene_file(ctx.city.eras.today)
    if not path.exists():
        raise StageError(f"no scene at {path}: run `qipu-map scene` first")
    return prepare_today(Scene.load(path), rules)


def _rules_digest(rules: EraRules) -> str:
    return value_digest(asdict(rules))


def write_past_scenes(ctx: Context, rules: EraRules, years: tuple[int, ...], *, force: bool = False) -> list[Path]:
    """Each year's scene, unless today's scene, its terrain, the year's evidence and the rules are unchanged."""
    work, today_year = ctx.work, ctx.city.eras.today
    today = load_today(ctx, rules)
    written = []
    for year in years:
        out = work.scene(year)
        evidence = load_evidence(ctx, rules, year)
        inputs = [work.scene_file(today_year), work.terrain(today_year)]
        if evidence is not None:
            inputs.append(work.evidence(evidence[0].name))
        params = {"version": VERSION, "year": year, "rules": _rules_digest(rules), "projection": asdict(ctx.projection)}
        key = cache.stage_key("eras scene", [p for p in inputs if p.is_file()], params)
        if not force and cache.is_fresh(out, key):
            log.info("%d: scene up to date", year)
            continue
        scene = derive_past_scene(today, year, rules, ctx.projection, evidence)
        out.mkdir(parents=True, exist_ok=True)
        scene.save(work.scene_file(year))
        if work.terrain(today_year).exists():
            shutil.copyfile(work.terrain(today_year), work.terrain(year))
        cache.mark_done(out, key)
        log.info("%d: %d buildings, %s", year, len(scene.buildings), scene.notes["eras"]["counts"])
        written.append(work.scene_file(year))
    return written


def _render_inputs(ctx: Context, year: int) -> list[Path]:
    """What stands for a year's render passes in a cache key: its frame plan and the render stage's own stamp."""
    return [ctx.work.frames(year), ctx.work.render(year) / cache.STAMP]


def write_layers_and_dates(ctx: Context, rules: EraRules, *, seed: int = 0, force: bool = False) -> list[Path]:
    """Every past year's layer, then every segment's date map. Returns the files written; fresh ones are skipped."""
    work, today_year, years = ctx.work, ctx.city.eras.today, ctx.city.eras.years
    if not work.canvas(today_year).is_file():
        raise StageError(f"no painted canvas at {work.canvas(today_year)}: run `qipu-map paint` first")
    today_paint = read_image(work.canvas(today_year), "RGBA")
    today_classes = np.asarray(load_canvas(work.render(today_year), "class"), dtype=np.uint8)
    written: list[Path] = []
    layers = {y: _layer(ctx, y, today_paint, today_classes, written, force=force) for y in years}
    shown = {y: composite(layer, shrink(today_paint, (layer.shape[1], layer.shape[0]))) for y, layer in layers.items()}
    shown[today_year] = today_paint
    scenes = {y: Scene.load(work.scene_file(y)) for y in years}
    scenes[today_year] = load_today(ctx, rules)
    origin = load_plan(work.render(today_year)).canvas.world_px
    for a, b in segments(years, today_year):
        inputs = [work.layer(y) if y != today_year else work.canvas(y) for y in (a, b)] + [work.canvas(today_year)]
        inputs += [work.scene_file(a), work.scene_file(b), work.scene_file(today_year)]
        inputs += _render_inputs(ctx, a) + _render_inputs(ctx, b)
        params = {"version": VERSION, "seed": seed, "rules": _rules_digest(rules)}
        key = cache.stage_key("eras dates", [p for p in inputs if p.is_file()], params)
        if not force and cache.is_fresh(work.switch(a, b), key):
            log.info("switch %d-%d: up to date", a, b)
            continue
        # A segment's date map has the size of its coarser year (past years may be painted a level or two up).
        size = min((shown[a].shape[1], shown[a].shape[0]), (shown[b].shape[1], shown[b].shape[0]))
        level = round(np.log2(today_paint.shape[1] / size[0]))
        changed = changed_mask(shrink(shown[a], size), shrink(shown[b], size))
        da, db = segment_building_dates(scenes[a].buildings, scenes[b].buildings, a, b)
        ids_a, ids_b = (
            shrink(np.asarray(load_canvas(work.render(y), "id"), np.int64), size, labels=True) for y in (a, b)
        )
        at = (origin[0] >> level, origin[1] >> level)
        dates = segment_dates(changed, building_pixels(ids_a, ids_b, da, db), a, b, seed=seed, origin=at)
        write_png(work.dates(a, b), to_rgb(encode_dates(dates)))
        cache.mark_done(work.switch(a, b), key)
        log.info("switch %d-%d: %.1f %% of pixels dated", a, b, 100.0 * float(np.mean(~np.isnan(dates))))
        written.append(work.dates(a, b))
    return written


def _layer(
    ctx: Context, year: int, today_paint: Pixels, today_classes: NDArray[np.uint8], written: list[Path], *, force: bool
) -> Pixels:
    """One year's layer: read back when its inputs did not change, else built and saved."""
    work, today_year = ctx.work, ctx.city.eras.today
    if not work.canvas(year).is_file():
        raise StageError(f"no painted canvas at {work.canvas(year)}: run `qipu-map paint --year {year}` first")
    inputs = [work.canvas(year), work.canvas(today_year), *_render_inputs(ctx, year), *_render_inputs(ctx, today_year)]
    key = cache.stage_key("eras layer", [p for p in inputs if p.is_file()], {"version": VERSION})
    if not force and cache.is_fresh(work.eras(year), key) and work.layer(year).is_file():
        return read_image(work.layer(year), "RGBA")
    painted = read_image(work.canvas(year), "RGBA")
    size = (painted.shape[1], painted.shape[0])
    classes = np.asarray(load_canvas(work.render(year), "class"), dtype=np.uint8)
    layer = past_layer(painted, shrink(today_paint, size), classes, shrink(today_classes, size, labels=True))
    write_png(work.layer(year), layer)
    cache.mark_done(work.eras(year), key)
    written.append(work.layer(year))
    return layer
