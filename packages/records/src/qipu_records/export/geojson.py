"""The map layer: one GeoJSON point for every placed place of every record."""

from __future__ import annotations

from typing import Any


def feature_collection(records: list[dict[str, Any]]) -> dict[str, Any]:
    """A FeatureCollection with one point per placed place of each decision."""
    features = []
    for record in records:
        for place in record["places"]:
            if "lat" not in place:
                continue
            properties = {key: record[key] for key in ("id", "date", "kind", "outcome", "summary", "quote", "zoning")}
            properties.update(
                place=place["text"],
                placed_as=place["placed_as"],
                page_url=record["source"]["page_url"],
                amounts=[m["amount"] for m in record["money"]],
                currency=record["money"][0]["currency"] if record["money"] else None,
            )
            point = {"type": "Point", "coordinates": [place["lon"], place["lat"]]}
            features.append({"type": "Feature", "geometry": point, "properties": properties})
    return {"type": "FeatureCollection", "features": features}
