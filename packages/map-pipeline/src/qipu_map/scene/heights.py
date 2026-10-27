"""How tall each building is: measured from the LiDAR where the reading can be trusted, else from OpenStreetMap, else a
default for its type.

The measurement: the height above ground of every 1 m cell inside the footprint drawn 1 m in
(DSM minus DEM of the same survey, so the vertical datum cancels), summarised by its median and upper percentiles.
Each guard below answers a way the reading was seen to go wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import shapely

from qipu_map.model import Raster
from qipu_map.scene.pixels import inset, inside, window

INSET_M = 1.0  # walls and eaves read half ground: measure inside them
MIN_CELLS = 12  # fewer cells than this is too few to trust a median
MAX_VOID = (
    0.15  # the 2025 survey left the tops of tall towers empty: a reading taken at their edges comes out far too low
)
LOW_M = 2.0  # a median under 2 m is a vacant lot or a demolished building in the survey, not a building
TALL_M = 12.0
PODIUM_P90_SHARE = (
    0.8  # a tower over a podium: the median reads the podium, the 90th percentile still reaches the tower
)
# Metres per storey, to count the storeys of a measured height. Ingest already turned OSM storey counts into heights
# by use (3.4 m for homes, 4.2 m for shops and offices); this one only applies to a storey count that came without one.
STOREY_M = 3.2


class HeightSource(StrEnum):
    LIDAR = "lidar"
    OSM = "osm"
    LEVELS = "levels"
    DEFAULT = "default"


@dataclass(frozen=True)
class Reading:
    """The LiDAR under one footprint: cells read, the share left empty by the survey, and height percentiles (m)."""

    cells: int
    void: float
    p10: float
    p50: float
    p90: float
    p95: float


@dataclass(frozen=True)
class Height:
    metres: float
    source: HeightSource
    why: str


def read(footprint: shapely.Polygon, dsm: Raster, dem: Raster) -> Reading | None:
    """The height distribution of the cells inside the footprint, or None when the rasters do not cover it."""
    if not dsm.same_grid(dem):
        raise ValueError("the DSM and DEM must be on one grid")
    poly = inset(footprint, INSET_M)
    top, ground = window(dsm, poly.bounds), window(dem, poly.bounds)
    if top.values.size == 0:
        return None
    mask = inside(top, poly)
    above = (top.values - ground.values)[mask]
    if above.size == 0:
        return None
    ok = above[np.isfinite(above)]
    void = 1.0 - ok.size / above.size
    if ok.size == 0:
        return Reading(0, void, 0.0, 0.0, 0.0, 0.0)
    p10, p50, p90, p95 = (float(v) for v in np.percentile(ok, [10, 50, 90, 95]))
    return Reading(int(ok.size), void, p10, p50, p90, p95)


def decide(reading: Reading | None, osm_m: float | None, levels: int | None, *, pitched: bool) -> Height | None:
    """The building's height above its ground (the ridge, for a pitched roof), or None to fall back to a type default.

    A pitched house stands to the LiDAR's ridge (95th percentile), anything else to its median.
    """
    record = _record(osm_m, levels)
    if reading is None or reading.cells < MIN_CELLS:
        return record
    measured = reading.p95 if pitched else reading.p50
    if reading.void > MAX_VOID:
        # Empty cells only pull a reading down, so a reading above the record is real (a tower built since).
        if record and measured > _same_band(record.metres) + record.metres:
            return Height(measured, HeightSource.LIDAR, "mostly void but above the record")
        return record
    if reading.p50 < LOW_M:
        return record
    if record is not None and _reads_podium(reading, record):
        return Height(record.metres, record.source, "the median reads the podium; the tower stands")
    return Height(measured, HeightSource.LIDAR, "measured")


def _reads_podium(reading: Reading, record: Height) -> bool:
    """A tall record, a median well under it and a 90th percentile that still reaches it: the median reads a podium."""
    low_median = reading.p50 < record.metres - _same_band(record.metres)
    return record.metres >= TALL_M and low_median and reading.p90 >= PODIUM_P90_SHARE * record.metres


def _record(osm_m: float | None, levels: int | None) -> Height | None:
    if osm_m is not None and osm_m > 0:
        return Height(osm_m, HeightSource.OSM, "OpenStreetMap height")
    if levels is not None and levels > 0:
        return Height(levels * STOREY_M, HeightSource.LEVELS, f"{levels} storeys at {STOREY_M} m")
    return None


def _same_band(metres: float) -> float:
    """How far two heights of one building may differ and still agree: 1.5 m or 15 %, calibrated on Vancouver
    buildings."""
    return max(1.5, 0.15 * metres)


def ground(footprint: shapely.Polygon, dem: Raster) -> float:
    """The building's ground: the mean of the terrain under its corners."""
    coords = shapely.get_coordinates(footprint.exterior)[:-1]
    values = dem.sample(coords[:, 0], coords[:, 1])
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if finite.size else 0.0
