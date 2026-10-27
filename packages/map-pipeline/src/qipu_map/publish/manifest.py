"""The release's manifest.json, in the `qipu-tiles/1` format of docs/tiles-format.md.

The manifest is all a viewer reads: where the canvas sits in the world, which layers exist down to which zoom, which
tiles of each are there, and whom to credit. It is built from what is on disk (each layer's `pyramid.json` and file
hashes) and the render's canvas, so it can never name a tile that was not written.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qipu_map.config import City
from qipu_map.geo.camera import Canvas
from qipu_map.hashing import file_digest
from qipu_map.tiles.pyramid import PYRAMID_FILE, Pyramid, zmax_for

FORMAT = "qipu-tiles/1"
VERSION_CHARS = 8
_SWITCH_DIR = re.compile(r"^(\d+)-(\d+)$")


@dataclass(frozen=True)
class Layer:
    """One pyramid on disk, as the manifest names it. `rel` is its folder relative to the release root."""

    rel: str
    pyramid: Pyramid
    digests: Mapping[str, str]

    @property
    def path(self) -> str:
        return f"{self.rel}/{{z}}/{{x}}/{{y}}{self.pyramid.suffix}"

    @property
    def version(self) -> str:
        """A short hash of the layer's tiles: their paths and contents, in order."""
        h = hashlib.sha256()
        for rel, digest in sorted(self.digests.items()):
            h.update(f"{rel}\0{digest}\n".encode())
        return h.hexdigest()[:VERSION_CHARS]

    def entry(self) -> dict[str, Any]:
        return {"path": self.path, "zmax": self.pyramid.zmax, "v": self.version, "have": self.pyramid.have()}


@dataclass(frozen=True)
class Layers:
    today: Layer
    years: Mapping[int, Layer]
    switch: Mapping[tuple[int, int], Layer]


def read_layer(root: Path, rel: str) -> Layer:
    """A pyramid folder under the release root, with the MD5 of every tile it lists."""
    folder = root / rel
    pyramid = Pyramid.load(folder)
    digests = {f"{rel}/{p}": file_digest(folder / p, "md5") for p in pyramid.paths()}
    return Layer(rel=rel, pyramid=pyramid, digests=digests)


def find_layers(root: Path) -> Layers:
    """Every finished pyramid under a tiles folder: `today/`, `years/<year>/`, `switch/<from>-<to>/`."""
    if not (root / "today" / PYRAMID_FILE).is_file():
        raise FileNotFoundError(f"no today pyramid in {root}: run `qipu-map tiles` first")
    years = {
        int(d.name): read_layer(root, f"years/{d.name}")
        for d in sorted((root / "years").glob("*"))
        if d.name.isdigit() and (d / PYRAMID_FILE).is_file()
    }
    switch = {}
    for d in sorted((root / "switch").glob("*")):
        m = _SWITCH_DIR.match(d.name)
        if m and (d / PYRAMID_FILE).is_file():
            switch[(int(m[1]), int(m[2]))] = read_layer(root, f"switch/{d.name}")
    return Layers(today=read_layer(root, "today"), years=years, switch=switch)


def switch_pairs(years: list[int], today: int) -> list[tuple[int, int]]:
    """The date-map segments a release needs: each past year to the next, the last one to today."""
    ends = [*sorted(years), today]
    return list(itertools.pairwise(ends))


def build_manifest(
    city: City, area: str, release: str, canvas: Canvas, layers: Layers, *, ground: str | None
) -> dict[str, Any]:
    """The manifest as a JSON-ready dict. Checks that the layers fit the canvas and that every segment has a date
    map."""
    tile_size = city.camera.tile_size
    zmax = zmax_for(canvas.width, canvas.height, tile_size)
    if layers.today.pyramid.zmax != zmax or layers.today.pyramid.tile_size != tile_size:
        raise ValueError(
            f"today's tiles go to zoom {layers.today.pyramid.zmax} at {layers.today.pyramid.tile_size} px, "
            f"the {canvas.width} x {canvas.height} canvas needs zoom {zmax} at {tile_size} px: re-run `qipu-map tiles`"
        )
    years = sorted(layers.years)
    needed = switch_pairs(years, city.eras.today) if years else []
    if sorted(layers.switch) != needed:
        raise ValueError(f"date maps on disk {sorted(layers.switch)} do not match the segments {needed}")
    camera = canvas.camera
    affine = canvas.affine()
    p = city.projection
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "city": city.id,
        "area": area,
        "release": release,
        "tile_size": tile_size,
        "canvas": {"width": canvas.width, "height": canvas.height, "metres_per_px": camera.metres_per_px, "zmax": zmax},
        "camera": {"azimuth_deg": camera.azimuth_deg, "elevation_deg": camera.elevation_deg},
        "projection": {
            "kind": "local-equirectangular",
            "lon0": p.lon0,
            "lat0": p.lat0,
            "metres_per_degree": p.metres_per_degree,
        },
        "world_to_px": [[_round(v) for v in row] for row in affine],
        "today": {"year": city.eras.today, **layers.today.entry()},
        "years": [{"year": y, **layers.years[y].entry()} for y in years],
        "switch": [{"from": a, "to": b, **layers.switch[(a, b)].entry()} for a, b in needed],
        "attribution": list(city.attribution),
    }
    if ground is not None:
        manifest["ground"] = ground
    return manifest


def _round(v: float) -> float:
    """Six decimals: a millionth of a pixel, and no float noise like -0.0 or 1e-17 in the file."""
    r = round(v, 6)
    return 0.0 if r == 0 else r
