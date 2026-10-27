"""FETCH: ask each source for the box and keep its answer in the raw folder. A file already there is not fetched
again."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial

import numpy as np
from numpy.typing import NDArray

from qipu_map.files import json_text
from qipu_map.geo.boxes import GeoBox
from qipu_map.geo.projection import LocalProjection
from qipu_map.ingest import lidar, opendata, overpass
from qipu_map.ingest.grid import LocalGrid, grid_bytes
from qipu_map.ingest.http import Http
from qipu_map.ingest.raw import RawStore
from qipu_map.ingest.sources import Source

log = logging.getLogger(__name__)

GridReader = Callable[[list[str], LocalGrid, LocalProjection], NDArray[np.float32]]

OPENDATA = ("footprints", "parcels", "trees", "parks", "streets", "lanes", "row_widths", "shoreline")
LIDAR_KINDS = ("dsm", "dem")


def raw_name(source_id: str) -> str:
    """The raw file a source is kept in."""
    if source_id in OPENDATA:
        return f"{source_id}.geojson"
    return {"tax_roll": "tax_roll.json", "osm": "osm.json", "lidar": "lidar_tiles.json"}[source_id]


def fetch_all(
    store: RawStore,
    *,
    sources: dict[str, Source],
    box: GeoBox,
    grid: LocalGrid,
    projection: LocalProjection,
    http: Http,
    read_grid: GridReader = lidar.read_grid,
) -> list[str]:
    """Fetch every source that is not in the raw folder yet. Returns the files written."""
    written = []
    for sid in OPENDATA:
        src = sources[sid]
        if store.fetch_once(sid, raw_name(sid), partial(opendata.dataset_in_box, http, src, box)):
            written.append(raw_name(sid))
    # the tax roll has no geometry: it is asked for the parcels the box holds
    parcels = store.read_json(raw_name("parcels"))
    coords = [str(f["properties"]["tax_coord"]) for f in parcels["features"] if f["properties"].get("tax_coord")]
    if store.fetch_once("tax_roll", raw_name("tax_roll"), lambda: opendata.tax_roll(http, sources["tax_roll"], coords)):
        written.append(raw_name("tax_roll"))
    if store.fetch_once("osm", raw_name("osm"), lambda: overpass.fetch(http, sources["osm"], box)):
        written.append(raw_name("osm"))
    written += _fetch_lidar(
        store, src=sources["lidar"], box=box, grid=grid, projection=projection, http=http, read_grid=read_grid
    )
    return written


def _fetch_lidar(
    store: RawStore,
    *,
    src: Source,
    box: GeoBox,
    grid: LocalGrid,
    projection: LocalProjection,
    http: Http,
    read_grid: GridReader,
) -> list[str]:
    written = []

    def index() -> bytes:
        return json_text({kind: lidar.tile_index(http, src, kind, box) for kind in LIDAR_KINDS}).encode()

    if store.fetch_once("lidar", raw_name("lidar"), index):
        written.append(raw_name("lidar"))
    tiles = store.read_json(raw_name("lidar"))
    for kind in LIDAR_KINDS:
        urls = [str(t["s3Url"]) for t in tiles[kind]]
        if not urls:
            raise RuntimeError(f"no {kind} tiles of {src.name} cover the area")
        name = f"lidar_{kind}.npz"
        if store.fetch_once("lidar", name, partial(_grid_file, read_grid, urls, grid, projection)):
            written.append(name)
    return written


def _grid_file(read_grid: GridReader, urls: list[str], grid: LocalGrid, projection: LocalProjection) -> bytes:
    return grid_bytes(grid, read_grid(urls, grid, projection))
