"""Paint one year's canvas: pre-tone, the shared half-resolution layer, the tiles with their guards, the quilt, the
protected surfaces and, if asked, the colour restore. Pure apart from the painter and the tile cache.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass as C
from qipu_map.config import Paint
from qipu_map.paint import anchor as anc
from qipu_map.paint.backends import RGB, Painter, Request, resize
from qipu_map.paint.colour import restore
from qipu_map.paint.grid import Grid, Tile, crop_reflect, seed_for
from qipu_map.paint.guards import judge
from qipu_map.paint.pretone import pretone
from qipu_map.paint.prompts import Choice, Content, Key, PromptSet, choose
from qipu_map.paint.protect import protect
from qipu_map.paint.quilt import quilt
from qipu_map.paint.tilecache import TileCache

log = logging.getLogger(__name__)

# A noise key names the noise field a painting starts from (see `noise`); it is part of the painting's cache key.
FIRST_NOISE = "nfC"  # the first painting of every tile and anchor
MAX_REROLLS = 2  # each re-roll is another model call; a tile still flagged after two is reported instead


def reroll_noise(k: int) -> str:
    """The noise key of a flagged tile's k-th re-roll: a fresh field, so the model paints the tile anew."""
    return f"nfR{k}"


@dataclass(frozen=True)
class Inputs:
    """The render's canvas passes and where the canvas sits in the world (its top-left in world pixels)."""

    beauty: RGB
    classes: NDArray[np.uint8]
    origin: tuple[int, int]


@dataclass(frozen=True)
class Options:
    """What varies per painted year: the year, today's year, an optional cap on tiles painted, and whether to restore
    colour."""

    year: int
    today: int
    max_tiles: int | None = None
    colour_restore: bool = False


@dataclass
class Report:
    painter: str
    year: int
    tiles: int = 0
    water_tiles: int = 0
    painted: int = 0
    reused: int = 0
    rerolled: int = 0
    still_flagged: list[str] = field(default_factory=list)
    left_as_render: int = 0
    anchors_painted: int = 0
    anchors_reused: int = 0
    keys: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Run:
    inputs: Inputs
    pre: RGB
    recipe: Paint
    painter: Painter
    prompts: PromptSet
    cache: TileCache
    options: Options
    report: Report

    def crop(self, image: NDArray[Any], x: int, y: int, size: int) -> NDArray[Any]:
        ox, oy = self.inputs.origin
        return crop_reflect(image, x - ox, y - oy, size, size)

    def call(self, req: Request) -> tuple[RGB, bool]:
        """(output, True if it came from the cache)."""
        digest = req.digest(self.painter.recipe)
        hit = self.cache.get(digest)
        if hit is not None:
            return hit, True
        out = self.painter.paint(req)
        self.cache.put(digest, out)
        return out, False

    def prompt(self, choice: Choice) -> str:
        return self.prompts.text(choice, self.options.year, self.options.today)


def paint_canvas(
    inputs: Inputs, recipe: Paint, painter: Painter, *, prompts: PromptSet, cache: TileCache, options: Options
) -> tuple[RGB, Report]:
    """Paint one year's canvas and return it with a report of tiles painted, reused, re-rolled and still flagged."""
    t0 = time.monotonic()
    report = Report(painter=painter.name, year=options.year)
    pre = pretone(inputs.beauty, inputs.classes, inputs.origin)
    run = _Run(inputs, pre, recipe, painter, prompts, cache, options, report)
    h, w = inputs.classes.shape
    grid = Grid(recipe.tile_px, recipe.stride_px, inputs.origin, w, h)
    tiles = grid.tiles()
    report.tiles = len(tiles)

    choices: dict[Tile, Choice] = {}
    for t in tiles:
        c = choose(Content.measure(run.crop(inputs.classes, t.x, t.y, recipe.tile_px)))
        if c is None:
            report.water_tiles += 1
        else:
            choices[t] = c
    todo = list(choices)
    if options.max_tiles is not None:
        report.left_as_render = max(0, len(todo) - options.max_tiles)
        todo = todo[: options.max_tiles]

    painted: dict[Tile, RGB] = {}
    if todo:
        layer = _layer(run, todo)
        for t in todo:
            painted[t] = _paint_tile(run, t, choices[t], layer)

    def load(x: int, y: int) -> NDArray[np.float32]:
        t = Tile(x, y)
        src = painted[t] if t in painted else run.crop(inputs.beauty, x, y, recipe.tile_px)
        return src.astype(np.float32)

    xs = sorted({t.x for t in tiles})
    ys = sorted({t.y for t in tiles})
    region = (xs[-1] + recipe.tile_px - xs[0], ys[-1] + recipe.tile_px - ys[0])
    ox, oy = inputs.origin
    walls = crop_reflect(inputs.classes == C.WALL, xs[0] - ox, ys[0] - oy, *region)
    joined = quilt(xs, ys, recipe.tile_px, load, walls)
    dx, dy = ox - xs[0], oy - ys[0]
    canvas: RGB = np.clip(joined[dy : dy + h, dx : dx + w] + 0.5, 0, 255).astype(np.uint8)
    canvas = protect(canvas, inputs.beauty, inputs.classes)
    if options.colour_restore:
        canvas = restore(canvas, inputs.beauty)
    report.seconds = round(time.monotonic() - t0, 1)
    return canvas, report


def _layer(run: _Run, todo: list[Tile]) -> anc.AnchorLayer:
    size = run.recipe.tile_px
    out: dict[anc.Anchor, RGB] = {}
    for a in anc.anchors_for(todo, size):
        x0, y0, n = a.window(size)
        choice = choose(Content.measure(run.crop(run.inputs.classes, x0, y0, n))) or Choice(Key.SHORE, False)
        lx, ly = a.half_res_origin(size)
        req = Request(
            images=(resize(run.crop(run.pre, x0, y0, n), size),),
            prompt=run.prompt(choice),
            seed=seed_for(a.x, a.y, run.recipe.seed),
            noise_key=FIRST_NOISE,
            level=anc.ANCHOR_LEVEL,
            x=lx,
            y=ly,
            size=size,
        )
        out[a], hit = run.call(req)
        if hit:
            run.report.anchors_reused += 1
        else:
            run.report.anchors_painted += 1
    return anc.join_layer(out, size)


def _paint_tile(run: _Run, t: Tile, choice: Choice, layer: anc.AnchorLayer) -> RGB:
    size = run.recipe.tile_px
    name = choice.key.value + ("_rail" if choice.rail else "")
    run.report.keys[name] = run.report.keys.get(name, 0) + 1
    render = run.crop(run.inputs.beauty, t.x, t.y, size)
    classes = run.crop(run.inputs.classes, t.x, t.y, size)
    base = Request(
        images=(layer.context(t, size), run.crop(run.pre, t.x, t.y, size)),
        prompt=run.prompts.anchored(run.prompt(choice)),
        seed=seed_for(t.x, t.y, run.recipe.seed),
        noise_key=FIRST_NOISE,
        level=anc.TILE_LEVEL,
        x=t.x,
        y=t.y,
        size=size,
    )
    best, hit = run.call(base)
    run.report.reused += hit
    run.report.painted += not hit
    verdict = judge(best, render, classes)
    if not verdict.flags:
        return best
    # A re-roll keeps the prompt and the layer and changes the noise key: with the noise passed in, a new seed alone
    # would paint the same tile again.
    run.report.rerolled += 1
    for k in range(1, MAX_REROLLS + 1):
        req = Request(base.images, base.prompt, base.seed, reroll_noise(k), base.level, base.x, base.y, base.size)
        cand, _ = run.call(req)
        v = judge(cand, render, classes)
        if v.cost < verdict.cost:
            best, verdict = cand, v
        if not verdict.flags:
            return best
    run.report.still_flagged.append(t.key)
    log.warning("tile %s still flagged after %d re-rolls: %s", t.key, MAX_REROLLS, ", ".join(verdict.flags))
    return best


def with_coverage(canvas: RGB, classes: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """The painted canvas as RGBA: opaque where the render shows the scene, transparent where it shows nothing (class
    NONE)."""
    alpha = np.where(classes == C.NONE, 0, 255).astype(np.uint8)
    return np.dstack([canvas, alpha])
