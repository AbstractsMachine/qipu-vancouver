"""The `qipu-map render` command."""

from __future__ import annotations

import argparse
from dataclasses import replace
from typing import Any

from qipu_map.context import Context, add_common, context_from_args
from qipu_map.errors import StageError
from qipu_map.render.job import CyclesSettings
from qipu_map.render.look import Light
from qipu_map.render.meshes import default_mesher
from qipu_map.render.stage import RenderSettings, render_year


def register(sub: Any) -> None:
    parser: argparse.ArgumentParser = sub.add_parser(
        "render", help="draw each year's scene through the map camera, in frames"
    )
    add_common(parser)
    parser.add_argument(
        "--backend", choices=("preview", "blender"), default="preview", help="preview (pure Python) or blender"
    )
    parser.add_argument("--year", type=int, default=None, help="one year (default: every year that has a scene)")
    parser.add_argument("--samples", type=int, default=None, help="Cycles samples per pixel (blender backend)")
    parser.add_argument("--device", default=None, help="Cycles device: OPTIX (rented GPUs), METAL, CUDA or CPU")
    parser.set_defaults(run=run)


def settings_from_args(ctx: Context, args: argparse.Namespace) -> RenderSettings:
    light = Light(sun_azimuth_deg=ctx.city.sun.azimuth_deg, sun_elevation_deg=ctx.city.sun.elevation_deg)
    cycles = CyclesSettings()
    if args.samples is not None:
        cycles = replace(cycles, samples=args.samples)
    if args.device is not None:
        cycles = replace(cycles, device=args.device.upper())
    return RenderSettings(backend=args.backend, light=light, cycles=cycles)


def run(args: argparse.Namespace) -> int:
    ctx = context_from_args(args)
    years = [args.year] if args.year is not None else ctx.work.scene_years()
    if not years:
        raise StageError(f"no scene to render under {ctx.work.base / 'scene'}: run `qipu-map scene` first")
    settings = settings_from_args(ctx, args)
    mesher = default_mesher()
    today = ctx.work.scene(ctx.city.eras.today)
    if not ctx.work.scene_file(ctx.city.eras.today).is_file():
        raise StageError(f"today's scene ({today}) sets every year's canvas: run `qipu-map scene` for it first")
    for year in years:
        render_year(ctx.work.scene(year), ctx.work.render(year), ctx.camera, settings, mesher, canvas_from=today)
    return 0
