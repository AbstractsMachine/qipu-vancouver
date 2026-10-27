"""Small builders for the ingest tests: GeoJSON collections, OSM elements and a fake HTTP layer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import shapely
from shapely.geometry import mapping

LON, LAT = -123.13, 49.28
D = 0.0001  # about 7 m east, 11 m north


def sq(x: float, y: float, w: float = 1.0, h: float = 1.0) -> shapely.Polygon:
    """A rectangle `w` by `h` units of D, its south-west corner `x`, `y` units of D from (LON, LAT)."""
    return shapely.box(LON + x * D, LAT + y * D, LON + (x + w) * D, LAT + (y + h) * D)


def pt(x: float, y: float) -> shapely.Point:
    return shapely.Point(LON + x * D, LAT + y * D)


def line(*xy: tuple[float, float]) -> shapely.LineString:
    return shapely.LineString([(LON + x * D, LAT + y * D) for x, y in xy])


def fc(*features: tuple[Any, dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(g), "properties": p} for g, p in features],
    }


def way(osm_id: int, geom: Any, **tags: str) -> dict[str, Any]:
    coords = list(geom.exterior.coords) if isinstance(geom, shapely.Polygon) else list(geom.coords)
    return {"type": "way", "id": osm_id, "tags": tags, "geometry": [{"lon": x, "lat": y} for x, y in coords]}


class FakeHttp:
    """Answers by URL substring and counts the calls."""

    def __init__(self, answers: Mapping[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict[str, str]]] = []

    def _answer(self, url: str, params: Mapping[str, str]) -> bytes:
        self.calls.append((url, dict(params)))
        for key, value in self.answers.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value if isinstance(value, bytes) else json.dumps(value).encode()
        raise OSError(f"no answer for {url}")

    def get(self, url: str, params: Mapping[str, str] | None = None) -> bytes:
        return self._answer(url, params or {})

    def post(self, url: str, form: Mapping[str, str]) -> bytes:
        return self._answer(url, form)
