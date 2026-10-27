"""NORMALISE: raw answers to the stage's layers. Pure apart from reading the raw folder and writing the outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from qipu_map.files import write_json
from qipu_map.geo.boxes import GeoBox, WorldBox
from qipu_map.ingest.fetch import LIDAR_KINDS, raw_name
from qipu_map.ingest.grid import load_grid
from qipu_map.ingest.normalise import buildings, nature, streets, water
from qipu_map.ingest.normalise.evidence import write_evidence
from qipu_map.ingest.normalise.geojson import write_layer
from qipu_map.ingest.raw import RawStore
from qipu_map.ingest.sources import Source

CLIP_INSET_DEG = 1e-6  # areas are cut a hair inside the fetch box, so a shoreline cropped to that box crosses the cut


@dataclass(frozen=True)
class IngestArea:
    """What normalising needs to know about the run's area."""

    geo: GeoBox  # the fetch box, degrees
    box: WorldBox  # the area itself, local metres
    margin_m: float
    scale: tuple[float, float]  # metres per degree east and north
    survey_year: int


def normalise(store: RawStore, sources: dict[str, Source], area: IngestArea, out: Path) -> dict[str, int]:
    """Write every layer, the height grids, any built-up masks and sources.json into `out`; return the count per
    layer."""
    raw = {sid: store.read_json(raw_name(sid)) for sid in sources if sid != "lidar"}
    clip = GeoBox(
        area.geo.south + CLIP_INSET_DEG,
        area.geo.west + CLIP_INSET_DEG,
        area.geo.north - CLIP_INSET_DEG,
        area.geo.east - CLIP_INSET_DEG,
    ).shape()
    sx, sy = area.scale
    parcels = buildings.ParcelIndex(raw["parcels"], buildings.parcels_from_roll(raw["tax_roll"]))
    survey = buildings.survey_buildings(raw["footprints"], parcels)
    layers = {
        "buildings": buildings.merge_osm(
            survey, buildings.osm_outlines(raw["osm"], sx * sy), parcels, area.survey_year
        ),
        "streets": streets.city_streets(raw["streets"], raw["lanes"], streets.RowWidths(raw["row_widths"], area.scale))
        + streets.osm_paths_and_rail(raw["osm"]),
        "trees": nature.trees(raw["trees"]),
        "parks": nature.parks(raw["parks"], clip),
        "water": water.water(raw["shoreline"], raw["osm"], clip),
    }
    counts = {name: write_layer(out / f"{name}.geojson", feats) for name, feats in layers.items()}
    cells = 0
    for kind in LIDAR_KINDS:
        grid = load_grid(store.path(f"lidar_{kind}.npz")).crop(area.box, area.margin_m)
        grid.save(out / f"{kind}.npz")
        cells += int(np.isfinite(grid.data).sum())
    write_evidence(store, out)
    records = {sid: _records(r) for sid, r in raw.items()} | {"lidar": cells}
    write_sources(out / "sources.json", sources, store.retrieved(), records)
    return counts


def _records(raw: Any) -> int:
    if isinstance(raw, list):
        return len(raw)
    return len(raw.get("features", raw.get("elements", [])))


def write_sources(path: Path, sources: dict[str, Source], retrieved: dict[str, str], records: dict[str, int]) -> None:
    """One entry per source: what it is, its licence and attribution line, when it was fetched and how many records it
    gave."""
    rows = [
        {
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "licence": s.licence,
            "attribution": s.attribution,
            "retrieved": retrieved.get(s.id),
            "features": records.get(s.id, 0),
        }
        for s in sorted(sources.values(), key=lambda s: s.id)
    ]
    write_json(path, rows)
