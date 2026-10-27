"""Reading raw GeoJSON and writing the stage's layers: sorted by id, coordinates rounded to 7 decimals (about 1 cm)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from qipu_map.files import write_json
from qipu_map.hashing import short_id

DECIMALS = 7


@dataclass(frozen=True)
class Feature:
    id: str
    geometry: BaseGeometry
    props: dict[str, Any]


def raw_features(fc: dict[str, Any]) -> Iterator[tuple[BaseGeometry, dict[str, Any]]]:
    """(geometry, properties) of every feature that has a geometry."""
    for f in fc.get("features", []):
        if f.get("geometry"):
            yield shape(f["geometry"]), dict(f.get("properties") or {})


def polygons(g: BaseGeometry) -> list[shapely.Polygon]:
    """The non-empty polygons in any geometry, largest first."""
    parts = [p for p in getattr(g, "geoms", [g]) if isinstance(p, shapely.Polygon) and not p.is_empty]
    return sorted(parts, key=lambda p: -p.area)


def lines(g: BaseGeometry) -> list[shapely.LineString]:
    return [p for p in getattr(g, "geoms", [g]) if isinstance(p, shapely.LineString) and len(p.coords) >= 2]


def split_ids(base: str, parts: list[Any]) -> list[str]:
    """One id per part: the base id alone when there is one part, else base#0, base#1..."""
    return [base] if len(parts) == 1 else [f"{base}#{i}" for i in range(len(parts))]


def shape_id(prefix: str, g: BaseGeometry) -> str:
    """A stable id for a feature its source does not number, from its rounded geometry."""
    return f"{prefix}-{short_id(_rounded(g).wkb)}"


def _rounded(g: BaseGeometry) -> BaseGeometry:
    return shapely.transform(g, lambda xy: np.round(xy, DECIMALS))


def collection(features: Iterable[Feature]) -> dict[str, Any]:
    feats = sorted(features, key=lambda f: f.id)
    ids = [f.id for f in feats]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate feature ids")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": f.id,
                "geometry": mapping(_rounded(f.geometry)),
                "properties": {"id": f.id, **f.props},
            }
            for f in feats
        ],
    }


def write_layer(path: Path, features: Iterable[Feature]) -> int:
    fc = collection(features)
    write_json(path, fc, compact=True)
    return len(fc["features"])
