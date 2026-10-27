"""Fetchers for an Opendatasoft portal (opendata.vancouver.ca runs one): a dataset cut to a box, and the tax roll."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import shapely

from qipu_map.files import json_text
from qipu_map.geo.boxes import GeoBox
from qipu_map.ingest.http import Http
from qipu_map.ingest.sources import Source

TAX_CHUNK = 150  # land coordinates per request: keeps the URL well under the portal's limit


def dataset_in_box(http: Http, source: Source, box: GeoBox) -> bytes:
    """Every record whose geometry touches the box, as GeoJSON, with only the fields the ingest reads.

    With `crop` set (the 2002 shoreline is two lines for the whole city, 1.2 MB) the geometries are cut to the box.
    """
    p = source.params
    params = {
        "where": f"intersects({p['geometry']}, geom'{box.wkt()}')",
        "select": ",".join(p["fields"]),
    }
    data = http.get(f"{p['portal']}/{p['dataset']}/exports/geojson", params)
    if not p.get("crop"):
        return data
    return json_text(crop_collection(json.loads(data), box), compact=True).encode()


def crop_collection(fc: dict[str, Any], box: GeoBox) -> dict[str, Any]:
    clip = box.shape()
    feats = []
    for f in fc["features"]:
        g = shapely.geometry.shape(f["geometry"]).intersection(clip)
        if not g.is_empty:
            feats.append({**f, "geometry": shapely.geometry.mapping(g)})
    return {"type": "FeatureCollection", "features": feats}


def tax_roll(http: Http, source: Source, land_coordinates: Iterable[str]) -> bytes:
    """The roll's rows for these parcels, one report year, as a JSON list."""
    p = source.params
    coords = sorted(set(land_coordinates))
    rows: list[Any] = []
    for i in range(0, len(coords), TAX_CHUNK):
        chunk = coords[i : i + TAX_CHUNK]
        listed = ",".join(f"'{c}'" for c in chunk)
        params = {
            "where": f"report_year='{p['report_year']}' and land_coordinate in ({listed})",
            "select": ",".join(p["fields"]),
        }
        rows.extend(json.loads(http.get(f"{p['portal']}/{p['dataset']}/exports/json", params)))
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return json_text(rows, compact=True).encode()
