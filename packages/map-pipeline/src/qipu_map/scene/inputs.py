"""Reading the ingest stage's files into local metres."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import shapely

from qipu_map.files import read_json
from qipu_map.geo.boxes import WorldBox
from qipu_map.geo.projection import LocalProjection
from qipu_map.scene.buildings import Footprint, clean
from qipu_map.scene.trees import Listed
from qipu_map.values import as_float, as_int

FILES = (
    "buildings.geojson",
    "streets.geojson",
    "trees.geojson",
    "parks.geojson",
    "water.geojson",
    "dsm.npz",
    "dem.npz",
)


def features(path: Path, proj: LocalProjection) -> Iterator[tuple[shapely.Geometry, dict[str, Any]]]:
    """Each feature's geometry in local metres, and its properties."""
    if not path.is_file():
        return
    for f in read_json(path)["features"]:
        if not f.get("geometry"):
            continue
        g = shapely.geometry.shape(f["geometry"])
        local = shapely.transform(g, lambda c: np.column_stack(proj.to_world(c[:, 0], c[:, 1])))
        yield local, f.get("properties") or {}


def footprints(path: Path, proj: LocalProjection, box: WorldBox) -> list[Footprint]:
    """The buildings that touch the box, with clean outlines, sorted by id."""
    area = box.shape()
    out = []
    for g, p in features(path, proj):
        poly = clean(g)
        if poly is None or not poly.intersects(area):
            continue
        out.append(
            Footprint(
                id=str(p["id"]),
                outline=poly,
                year_built=as_int(p.get("year_built")),
                year_source=p.get("year_source"),
                year_improved=as_int(p.get("year_improved")),
                height_m=as_float(p.get("height_m")),
                levels=as_int(p.get("levels")),
                use=p.get("use"),
            )
        )
    return sorted(out, key=lambda f: f.id)


def listed_trees(path: Path, proj: LocalProjection, box: WorldBox) -> list[Listed]:
    x0, y0, x1, y1 = box
    out = []
    for g, p in features(path, proj):
        if not isinstance(g, shapely.Point) or not (x0 <= g.x <= x1 and y0 <= g.y <= y1):
            continue
        out.append(
            Listed(
                str(p["id"]),
                round(g.x, 2),
                round(g.y, 2),
                p.get("genus"),
                as_float(p.get("height_m")),
                as_float(p.get("diameter_cm")),
                as_int(p.get("year_planted")),
            )
        )
    return sorted(out, key=lambda t: t.id)
