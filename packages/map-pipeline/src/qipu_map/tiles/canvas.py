"""Cut an image into its pyramid: today's painted canvas and each past year's layer as WebP, each segment's date map as
PNG.

A past year can be painted at a coarser scale than today (the San Francisco eras were rendered one or two levels above
the present). Its image must then be exactly one of today's zoom levels in size, so its tiles sit on the same grid;
anything else is refused.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from qipu_map.cache import is_fresh, mark_done, stage_key
from qipu_map.eras.datecodec import NEVER, encode_png, from_rgb, is_never, reduce_min
from qipu_map.errors import StageError
from qipu_map.imageio import Pixels, image_size, read_image
from qipu_map.imageops import halve_rgba
from qipu_map.tiles.images import WEBP_METHOD, WEBP_QUALITY, encode_webp, is_near_black
from qipu_map.tiles.pyramid import Pyramid, cut_tile, level_size, write_pyramid, zmax_for

log = logging.getLogger(__name__)

WEBP = ".webp"
PNG = ".png"


class TileError(StageError):
    """An image that cannot be published as it is."""


@dataclass(frozen=True)
class TileJob:
    """One pyramid to cut: `source` is a painted RGBA image, or with `dates` a date map (eras/switch/*/dates.png)."""

    name: str
    source: Path
    out_dir: Path
    dates: bool = False


def layer_zoom(today_size: tuple[int, int], size: tuple[int, int], tile_size: int) -> int:
    """The zoom of today's pyramid that an image of `size` matches, or a TileError."""
    zmax = zmax_for(*today_size, tile_size)
    for z in range(zmax, -1, -1):
        if level_size(*today_size, zmax, z) == size:
            return z
    raise TileError(
        f"a {size[0]} x {size[1]} image is none of the zoom levels of the {today_size[0]} x {today_size[1]} canvas"
    )


def dark_tiles(image: Pixels, tile_size: int) -> list[tuple[int, int]]:
    """The deepest-level tiles whose painted pixels are all near black."""
    h, w = image.shape[:2]
    return [
        (x, y)
        for y in range(-(-h // tile_size))
        for x in range(-(-w // tile_size))
        if is_near_black(cut_tile(image, x, y, tile_size))
    ]


def tile_job(
    job: TileJob, *, tile_size: int, today_size: tuple[int, int] | None = None, force: bool = False
) -> Pyramid:
    """Write one pyramid, unless its source and the settings are unchanged since the last run."""
    params = {"tile_size": tile_size, "quality": WEBP_QUALITY, "method": WEBP_METHOD, "dates": job.dates}
    key = stage_key("tiles", [job.source], params)
    if not force and is_fresh(job.out_dir, key):
        log.info("%s: unchanged, kept", job.name)
        return Pyramid.load(job.out_dir)
    if today_size is not None:
        layer_zoom(today_size, image_size(job.source), tile_size)
    if job.dates:
        codes = from_rgb(read_image(job.source, "RGB"))
        encode = partial(encode_png, tile_size=tile_size)
        pyramid = write_pyramid(
            codes,
            job.out_dir,
            tile_size=tile_size,
            encode=encode,
            reduce=reduce_min,
            suffix=PNG,
            is_empty=is_never,
            fill=NEVER,
        )
    else:
        image = read_image(job.source, "RGBA")
        dark = dark_tiles(image, tile_size)
        if dark:
            raise TileError(
                f"{job.name}: {len(dark)} near-black tiles, first {dark[:5]}; a broken frame or paint pass?"
            )
        pyramid = write_pyramid(
            image, job.out_dir, tile_size=tile_size, encode=encode_webp, reduce=halve_rgba, suffix=WEBP
        )
    mark_done(job.out_dir, key)
    count = sum(len(t) for t in pyramid.tiles.values())
    log.info("%s: zmax %d, %d tiles", job.name, pyramid.zmax, count)
    return pyramid
