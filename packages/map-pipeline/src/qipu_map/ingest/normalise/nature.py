"""Public trees and parks, from the City."""

from __future__ import annotations

from typing import Any

import shapely

from qipu_map.ingest.normalise.geojson import Feature, polygons, raw_features, split_ids
from qipu_map.values import as_positive, as_text, year_in


def trees(raw: dict[str, Any]) -> list[Feature]:
    """Boulevard and park trees. The planting date is read when the dataset publishes one (it has not since 2025)."""
    out = []
    for g, p in raw_features(raw):
        if not isinstance(g, shapely.Point):
            continue
        props = {
            "genus": as_text(p.get("genus_name")),
            "species": as_text(p.get("species_name")),
            "height_m": as_positive(p.get("height_m")),
            "diameter_cm": as_positive(p.get("diameter_cm")),
            "year_planted": year_in(p.get("date_planted")),
        }
        out.append(Feature(f"tree-{p['asset_id']}", g, props))
    return out


def parks(raw: dict[str, Any], clip: shapely.Polygon) -> list[Feature]:
    """Park polygons cut to the box: a park the size of Stanley Park only matters where it meets the area."""
    out = []
    for g, p in raw_features(raw):
        parts = polygons(g.intersection(clip))
        for fid, part in zip(split_ids(f"park-{p['object_id']}", parts), parts, strict=True):
            out.append(Feature(fid, part, {"name": as_text(p.get("park_name"))}))
    return out
