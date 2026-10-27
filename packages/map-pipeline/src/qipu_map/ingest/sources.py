"""The open datasets the ingest reads, with their licences.

A city file can override any of these through a `[sources.<id>]` table (same field names); the defaults below are
Vancouver's, so the stage works for Vancouver with no `[sources]` table at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

OGL_VANCOUVER = "Open Government Licence – Vancouver"
OGL_BC = "Open Government Licence – British Columbia"
ODBL = "Open Database Licence (ODbL) 1.0"

_ATTR_VANCOUVER = "Contains information licensed under the Open Government Licence – Vancouver."
_ATTR_BC = "Contains information licensed under the Open Government Licence – British Columbia."
_ATTR_OSM = "© OpenStreetMap contributors (ODbL)."

VANCOUVER_PORTAL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"


@dataclass(frozen=True)
class Source:
    """One dataset. `kind` says which fetcher reads it; `params` are that fetcher's settings."""

    id: str
    name: str
    url: str
    licence: str
    attribution: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


def _city_dataset(sid: str, name: str, dataset: str, fields: tuple[str, ...], *, crop: bool = False) -> Source:
    return Source(
        id=sid,
        name=f"City of Vancouver: {name}",
        url=f"https://opendata.vancouver.ca/explore/dataset/{dataset}/",
        licence=OGL_VANCOUVER,
        attribution=_ATTR_VANCOUVER,
        kind="opendata",
        params={
            "portal": VANCOUVER_PORTAL,
            "dataset": dataset,
            "fields": list(fields),
            "geometry": "geom",
            "crop": crop,
        },
    )


VANCOUVER: dict[str, Source] = {
    s.id: s
    for s in (
        _city_dataset("footprints", "Building Footprints 2015", "building-footprints-2015", ("object_id", "geom")),
        _city_dataset("parcels", "Property parcel polygons", "property-parcel-polygons", ("tax_coord", "geom")),
        Source(
            id="tax_roll",
            name="City of Vancouver: Property tax report",
            url="https://opendata.vancouver.ca/explore/dataset/property-tax-report/",
            licence=OGL_VANCOUVER,
            attribution=_ATTR_VANCOUVER,
            kind="tax_roll",
            params={
                "portal": VANCOUVER_PORTAL,
                "dataset": "property-tax-report",
                "fields": ["land_coordinate", "year_built", "big_improvement_year", "zoning_district"],
                "report_year": "2026",
            },
        ),
        _city_dataset(
            "trees",
            "Public trees",
            "public-trees",
            ("asset_id", "genus_name", "species_name", "height_m", "diameter_cm", "geom"),
        ),
        _city_dataset(
            "parks",
            "Parks - polygon representation",
            "parks-polygon-representation",
            ("object_id", "park_name", "geom"),
        ),
        _city_dataset("streets", "Public streets", "public-streets", ("hblock", "streetuse", "geom")),
        _city_dataset("lanes", "Lanes", "lanes", ("std_street", "geom")),
        _city_dataset("row_widths", "Right-of-way widths", "right-of-way-widths", ("width", "geom")),
        _city_dataset("shoreline", "Shoreline 2002", "shoreline-2002", ("geom",), crop=True),
        Source(
            id="osm",
            name="OpenStreetMap",
            url="https://www.openstreetmap.org/copyright",
            licence=ODBL,
            attribution=_ATTR_OSM,
            kind="overpass",
            params={
                "endpoints": [
                    "https://overpass-api.de/api/interpreter",
                    "https://overpass.kumi.systems/api/interpreter",
                    "https://overpass.private.coffee/api/interpreter",
                ]
            },
        ),
        Source(
            id="lidar",
            name="LidarBC 2025: 1 m digital surface and elevation models",
            url="https://www2.gov.bc.ca/gov/content/data/geographic-data-services/lidarbc",
            licence=OGL_BC,
            attribution=_ATTR_BC,
            kind="lidar",
            params={
                "index": "https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/LiDAR_BC_S3_Public/FeatureServer",
                "layers": {"dsm": 1, "dem": 5},
                "year": 2025,
            },
        ),
    )
}


def sources_for(overrides: dict[str, dict[str, Any]]) -> dict[str, Source]:
    """The default sources with a city file's `[sources.*]` tables laid over them."""
    out = dict(VANCOUVER)
    for sid, table in overrides.items():
        base = out.get(sid)
        if base is None:
            out[sid] = Source(id=sid, **table)
            continue
        params = {**base.params, **table.get("params", {})}
        out[sid] = replace(base, **{k: v for k, v in table.items() if k != "params"}, params=params)
    return out
