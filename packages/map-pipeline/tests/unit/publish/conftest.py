import io
import itertools
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from qipu_map.config import City, load_city
from qipu_map.geo.camera import Canvas, ObliqueCamera
from qipu_map.imageops import halve_rgba
from qipu_map.model import Raster
from qipu_map.paths import WorkDir
from qipu_map.render.frames import plan_frames, save_plan
from qipu_map.tiles.images import encode_webp
from qipu_map.tiles.pyramid import write_pyramid

TILE = 16
CANVAS = Canvas(ObliqueCamera(0.0, 30.709, 0.25), -100.0, 250.0, 40, 30)


@pytest.fixture
def city() -> City:
    c = load_city("vancouver")
    return replace(c, camera=replace(c.camera, tile_size=TILE), eras=replace(c.eras, years=(1950, 1972)))


def _min_halve(a: NDArray[np.uint8]) -> NDArray[np.uint8]:
    h, w = -(-a.shape[0] // 2) * 2, -(-a.shape[1] // 2) * 2
    p = np.full((h, w, 3), 255, dtype=np.uint8)
    p[: a.shape[0], : a.shape[1]] = a
    out: NDArray[np.uint8] = p.reshape(h // 2, 2, w // 2, 2, 3).min(axis=(1, 3))
    return out


def _png(tile: NDArray[np.uint8]) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(tile).save(buf, "PNG")
    return buf.getvalue()


def make_work(root: Path, *, years: tuple[int, ...] = (1950, 1972), switch: bool = True) -> WorkDir:
    """A tiny finished run: a 40 x 30 canvas, past years at the level above, date maps, frames.json and terrain."""
    work = WorkDir(root, "ca/vancouver", "west-end")
    rng = np.random.default_rng(5)
    today = rng.integers(40, 220, (30, 40, 4), dtype=np.uint8)
    today[..., 3] = 255
    today[:16, :16, 3] = 0
    write_pyramid(today, work.today_tiles(), tile_size=TILE, encode=encode_webp, reduce=halve_rgba, suffix=".webp")
    for y in years:
        past = halve_rgba(today)
        past[..., 3] = 0
        past[4:9, 4:9, 3] = 255
        write_pyramid(past, work.year_tiles(y), tile_size=TILE, encode=encode_webp, reduce=halve_rgba, suffix=".webp")
    if switch:
        ends = [*years, 2026]
        for a, b in itertools.pairwise(ends):
            date = np.zeros((30, 40, 3), dtype=np.uint8)
            date[..., :2] = 255
            write_pyramid(
                date,
                work.switch_tiles(a, b),
                tile_size=TILE,
                encode=_png,
                reduce=_min_halve,
                suffix=".png",
                is_empty=lambda t: False,
            )
    save_plan(plan_frames(CANVAS), 2026, work.render(2026))
    work.scene(2026).mkdir(parents=True)
    Raster(x0=-60.0, y0=80.0, cell=1.0, data=np.full((60, 70), 12.34, dtype=np.float32)).save(
        work.scene(2026) / "terrain.npz"
    )
    return work
