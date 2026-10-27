"""LiDAR surface (DSM) and bare-earth (DEM) grids, read from LidarBC's 1 m GeoTIFF tiles over HTTP.

The province publishes a tile index (an ArcGIS FeatureServer, one layer per product, field `s3Url`). Only the window
each tile shares with the area is read: GDAL fetches the byte ranges it needs, so a run never downloads whole tiles.
Height above ground is DSM − DEM of the same survey; the two are never mixed across surveys because their vertical
datums differ.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray

from qipu_map.geo.boxes import GeoBox
from qipu_map.geo.projection import LocalProjection
from qipu_map.ingest.grid import LocalGrid, fill_missing, sample_nearest
from qipu_map.ingest.http import Http
from qipu_map.ingest.sources import Source

log = logging.getLogger(__name__)

# Remote GeoTIFF reads: do not list the bucket, merge neighbouring byte ranges, cache blocks.
GDAL_HTTP_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
}


def tile_index(http: Http, source: Source, kind: str, box: GeoBox) -> list[dict[str, Any]]:
    """The tiles of one product (dsm or dem) and year that touch the box, sorted by file name."""
    p = source.params
    params = {
        "where": f"year={int(p['year'])}",
        "geometry": f"{box.west},{box.south},{box.east},{box.north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "filename,s3Url",
        "returnGeometry": "false",
        "f": "json",
    }
    data = json.loads(http.get(f"{p['index']}/{p['layers'][kind]}/query", params))
    tiles = [f["attributes"] for f in data.get("features", [])]
    return sorted(tiles, key=lambda t: str(t["filename"]))


def read_grid(urls: list[str], grid: LocalGrid, projection: LocalProjection) -> NDArray[np.float32]:
    """The tiles sampled at the grid's cell centres (nearest cell), NaN where no tile has a value. Needs the `lidar`
    extra."""
    import rasterio  # noqa: PLC0415 (the lidar extra)
    from pyproj import Transformer  # noqa: PLC0415
    from rasterio.windows import from_bounds  # noqa: PLC0415

    xx, yy = grid.centres()
    lon, lat = projection.to_lonlat(xx, yy)
    out = np.full(xx.shape, np.nan, np.float32)
    with rasterio.Env(**GDAL_HTTP_ENV):
        for url in urls:
            with rasterio.open(f"/vsicurl/{url}" if url.startswith("http") else url) as src:
                ex, ny = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(lon, lat)
                win = from_bounds(ex.min() - 2, ny.min() - 2, ex.max() + 2, ny.max() + 2, src.transform)
                win = win.round_offsets().round_lengths()
                data = src.read(1, window=win, boundless=True, fill_value=src.nodata)
                t = src.window_transform(win)
                vals = sample_nearest(data, (t.a, t.b, t.c, t.d, t.e, t.f), src.nodata, np.asarray(ex), np.asarray(ny))
            out = fill_missing(out, vals)
            log.info("lidar %s: %d cells filled so far", url.rsplit("/", 1)[-1], int(np.isfinite(out).sum()))
    return out
