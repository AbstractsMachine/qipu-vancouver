"""The map layer: one GeoJSON point for every placed place of every record."""

from __future__ import annotations

from typing import Literal, TypedDict

from qipu_records.export.records import DecisionRecord


class FeatureProperties(TypedDict):
    id: str
    date: str | None
    kind: str
    outcome: str
    summary: str
    quote: str
    zoning: str | None
    place: str
    placed_as: str
    page_url: str | None
    amounts: list[float | None]
    currency: str | None


class Point(TypedDict):
    type: Literal["Point"]
    coordinates: list[float]


class Feature(TypedDict):
    type: Literal["Feature"]
    geometry: Point
    properties: FeatureProperties


class FeatureCollection(TypedDict):
    type: Literal["FeatureCollection"]
    features: list[Feature]


def feature_collection(records: list[DecisionRecord]) -> FeatureCollection:
    """A FeatureCollection with one point per placed place of each decision."""
    features: list[Feature] = []
    for record in records:
        for place in record["places"]:
            if "lat" not in place or "lon" not in place:
                continue
            properties: FeatureProperties = {
                "id": record["id"],
                "date": record["date"],
                "kind": record["kind"],
                "outcome": record["outcome"],
                "summary": record["summary"],
                "quote": record["quote"],
                "zoning": record["zoning"],
                "place": place["text"],
                "placed_as": place.get("placed_as", ""),
                "page_url": record["source"]["page_url"],
                "amounts": [m["amount"] for m in record["money"]],
                "currency": record["money"][0]["currency"] if record["money"] else None,
            }
            point: Point = {"type": "Point", "coordinates": [place["lon"], place["lat"]]}
            features.append({"type": "Feature", "geometry": point, "properties": properties})
    return {"type": "FeatureCollection", "features": features}
