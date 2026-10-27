"""OpenStreetMap through the Overpass API: one query for every layer the ingest reads from OSM."""

from __future__ import annotations

import json

from qipu_map.files import json_text
from qipu_map.geo.boxes import GeoBox
from qipu_map.ingest.http import Http, post_first
from qipu_map.ingest.sources import Source


def query(box: GeoBox, timeout_s: int = 180) -> str:
    """Buildings, streets and paths, rail, water bodies and the coastline, with tags and full geometry."""
    b = box.overpass()
    parts = [
        f'way["building"]{b};',
        f'relation["building"]{b};',
        f'way["highway"]{b};',
        f'way["railway"]{b};',
        f'way["natural"="water"]{b};',
        f'relation["natural"="water"]{b};',
        f'way["natural"="coastline"]{b};',
        f'way["waterway"="riverbank"]{b};',
    ]
    return f"[out:json][timeout:{timeout_s}];(" + "".join(parts) + ");out tags geom;"


def fetch(http: Http, source: Source, box: GeoBox) -> bytes:
    data = post_first(http, source.params["endpoints"], {"data": query(box)})
    elements = json.loads(data)["elements"]  # an error page is not JSON with elements: fail here, not in normalise
    elements.sort(key=lambda e: (e["type"], e["id"]))
    return json_text({"elements": elements}, compact=True).encode()
