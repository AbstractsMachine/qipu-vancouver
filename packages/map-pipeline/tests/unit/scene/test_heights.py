from __future__ import annotations

import numpy as np
import pytest
import shapely

from qipu_map.model import Raster
from qipu_map.scene.heights import STOREY_M, HeightSource, Reading, decide, ground, read
from tests.unit.scene import synth

HOUSE = shapely.box(*synth.HOUSE)


def reading(
    p50: float, p90: float | None = None, *, cells: int = 100, void: float = 0.0, p95: float | None = None
) -> Reading:
    return Reading(
        cells, void, p50 * 0.8, p50, p90 if p90 is not None else p50, p95 if p95 is not None else (p90 or p50)
    )


def test_read_measures_inside_the_inset_footprint() -> None:
    r = read(HOUSE, synth.flat(10.0), synth.grid())
    assert r is not None
    assert r.p50 == pytest.approx(10.0)
    assert r.cells == 8 * 14  # 1 m in from each wall
    assert r.void == 0.0


def test_read_counts_void_cells() -> None:
    dsm = synth.flat(10.0)
    data = dsm.data.copy()
    data[20:26, 11:19] = np.nan
    r = read(HOUSE, Raster(dsm.x0, dsm.y0, dsm.cell, data), synth.grid())
    assert r is not None
    assert 0.3 < r.void < 0.5
    assert r.p50 == pytest.approx(10.0)


def test_read_outside_the_rasters() -> None:
    assert read(shapely.box(100, 100, 110, 110), synth.flat(), synth.grid()) is None


def test_read_refuses_rasters_on_different_grids() -> None:
    dem = synth.grid()
    with pytest.raises(ValueError, match="one grid"):
        read(HOUSE, synth.flat(10.0), Raster(dem.x0 + 0.5, dem.y0, dem.cell, dem.data))


def test_read_all_void() -> None:
    dsm = synth.grid(np.nan)
    r = read(HOUSE, dsm, synth.grid())
    assert r is not None
    assert r.cells == 0
    assert r.void == 1.0


def test_measured_median_wins() -> None:
    h = decide(reading(9.6), osm_m=12.0, levels=None, pitched=False)
    assert h is not None
    assert h.source is HeightSource.LIDAR
    assert h.metres == 9.6


def test_pitched_roof_stands_to_its_ridge() -> None:
    h = decide(reading(7.0, 9.0, p95=9.5), osm_m=None, levels=None, pitched=True)
    assert h is not None
    assert h.metres == 9.5


def test_too_few_cells_fall_back_to_osm_then_levels_then_nothing() -> None:
    few = reading(9.0, cells=5)
    assert decide(few, osm_m=11.0, levels=3, pitched=False) == decide(None, 11.0, None, pitched=False)
    by_levels = decide(few, osm_m=None, levels=3, pitched=False)
    assert by_levels is not None
    assert by_levels.source is HeightSource.LEVELS
    assert by_levels.metres == pytest.approx(3 * STOREY_M)
    assert decide(few, osm_m=None, levels=None, pitched=False) is None


def test_void_tops_keep_the_record() -> None:
    """The 2025 survey dropped tall tower tops: a reading taken at their edges is far too low."""
    h = decide(reading(20.0, void=0.4), osm_m=110.0, levels=None, pitched=False)
    assert h is not None
    assert h.source is HeightSource.OSM
    assert h.metres == 110.0


def test_void_but_above_the_record_is_real() -> None:
    h = decide(reading(150.0, void=0.4), osm_m=35.0, levels=None, pitched=False)
    assert h is not None
    assert h.source is HeightSource.LIDAR
    assert h.metres == 150.0


def test_a_vacant_lot_keeps_the_record() -> None:
    assert decide(reading(0.4), osm_m=None, levels=None, pitched=False) is None


def test_tower_over_a_podium_keeps_the_record() -> None:
    h = decide(reading(9.0, 100.0), osm_m=112.0, levels=None, pitched=False)
    assert h is not None
    assert h.source is HeightSource.OSM
    assert h.metres == 112.0


def test_a_tall_record_without_a_tower_in_the_survey_is_replaced() -> None:
    h = decide(reading(9.0, 11.0), osm_m=40.0, levels=None, pitched=False)
    assert h is not None
    assert h.source is HeightSource.LIDAR
    assert h.metres == 9.0


def test_ground_is_the_mean_under_the_corners() -> None:
    dem = synth.grid()
    x, _y = synth.centres(dem)
    sloped = Raster(dem.x0, dem.y0, dem.cell, (10.0 + 0.1 * x).astype(np.float32))
    assert ground(HOUSE, sloped) == pytest.approx(10.0 + 0.1 * 15.0, abs=0.01)
    assert ground(HOUSE, synth.grid(np.nan)) == 0.0
