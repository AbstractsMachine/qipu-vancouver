"""The scene command end to end, on a tiny made-up West End: a gabled house, a tower, a tree, a street, a park, the
sea."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely

from qipu_map.cli import main
from qipu_map.config import load_city
from qipu_map.geo.projection import LocalProjection
from qipu_map.model import BuildingType, Raster, RoofForm, Scene
from qipu_map.paths import WorkDir

CITY = load_city("vancouver")
PROJ = LocalProjection.from_config(CITY.projection)
BOX = PROJ.box_to_world(CITY.area("west-end").bbox)


def lonlat(points: list[tuple[float, float]]) -> list[list[float]]:
    return [list(PROJ.to_lonlat(x, y)) for x, y in points]


def feature(fid: str, geometry: str, coords: Any, **props: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": geometry, "coordinates": coords},
        "properties": {"id": fid, **props},
    }


def write(path: Path, features: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def box_ring(x0: float, y0: float, x1: float, y1: float) -> list[list[list[float]]]:
    return [lonlat([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])]


def make_ingest(folder: Path) -> tuple[float, float]:
    """Writes the ingest files; returns the house's south-west corner."""
    folder.mkdir(parents=True)
    x0, y0, x1, y1 = BOX
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = int(x1 - x0) + 40, int(y1 - y0) + 40
    gx, gy = np.meshgrid(x0 - 20 + np.arange(w) + 0.5, y1 + 20 - np.arange(h) - 0.5)
    dem = np.full((h, w), 5.0)
    dsm = dem.copy()
    house = (gx > cx) & (gx < cx + 10) & (gy > cy) & (gy < cy + 16)
    dsm[house] += 6.0 + 0.9 * (5.0 - np.abs(gx[house] - (cx + 5)))
    tower = (gx > cx - 60) & (gx < cx - 35) & (gy > cy) & (gy < cy + 25)
    dsm[tower] += 58.0
    dsm += np.maximum(0.0, 11.0 - 1.6 * np.hypot(gx - (cx + 40.5), gy - (cy + 40.5)))
    for name, data in (("dsm", dsm), ("dem", dem)):
        Raster(x0 - 20, y1 + 20, 1.0, data.astype(np.float32)).save(folder / f"{name}.npz")
    write(
        folder / "buildings.geojson",
        [
            feature(
                "house",
                "Polygon",
                box_ring(cx, cy, cx + 10, cy + 16),
                year_built=1908,
                year_source="tax_roll",
                use="RT-8",
            ),
            feature(
                "tower",
                "Polygon",
                box_ring(cx - 60, cy, cx - 35, cy + 25),
                year_built=1968,
                year_source="tax_roll",
                use="RM-5A",
            ),
        ],
    )
    write(
        folder / "streets.geojson",
        [feature("davie", "LineString", lonlat([(x0 - 50, cy - 20), (x1 + 50, cy - 20)]), kind="arterial")],
    )
    write(
        folder / "trees.geojson",
        [feature("t1", "Point", lonlat([(cx - 10, cy - 12)])[0], genus="ACER", height_m=9.0, diameter_cm=30.0)],
    )
    write(
        folder / "parks.geojson",
        [feature("nelson", "Polygon", box_ring(cx + 30, cy + 30, cx + 60, cy + 60), name="Nelson Park")],
    )
    write(
        folder / "water.geojson",
        [feature("bay", "Polygon", box_ring(x0 - 100, y0 - 100, x1 + 100, y0 + 50), kind="sea")],
    )
    return cx, cy


def test_scene_command_builds_and_caches(tmp_path: Path) -> None:
    work = WorkDir(tmp_path, CITY.id, "west-end")
    make_ingest(work.ingest)
    assert main(["scene", "--work", str(tmp_path), "--area", "west-end"]) == 0

    out = work.scene(CITY.eras.today)
    scene = Scene.load(out / "scene.json")
    by_id = {b.id: b for b in scene.buildings}
    assert by_id["house"].roof is RoofForm.GABLE
    assert by_id["house"].kind is BuildingType.CHARACTER_HOUSE
    assert by_id["tower"].kind is BuildingType.POINT_TOWER
    assert by_id["tower"].height_m == pytest.approx(58.0)
    assert by_id["house"].ground_m == pytest.approx(5.0)
    assert scene.notes["trees"] == {"street": 1, "canopy": 1}
    assert [s.width_m for s in scene.streets] == [15.0]
    assert [p.name for p in scene.parks] == ["Nelson Park"]
    land_and_water = sum(shapely.Polygon(p.outer, p.holes).area for p in scene.land + scene.water)
    assert land_and_water == pytest.approx((BOX[2] - BOX[0]) * (BOX[3] - BOX[1]), rel=1e-6)
    terrain = Raster.load(out / scene.terrain_file)
    assert float(terrain.data.mean()) == pytest.approx(5.0)

    written = (out / "scene.json").stat().st_mtime_ns
    assert main(["scene", "--work", str(tmp_path), "--area", "west-end"]) == 0
    assert (out / "scene.json").stat().st_mtime_ns == written
    first = (out / "scene.json").read_bytes()
    assert main(["scene", "--work", str(tmp_path), "--area", "west-end", "--force"]) == 0
    assert (out / "scene.json").read_bytes() == first


def test_scene_command_needs_ingest(tmp_path: Path) -> None:
    assert main(["scene", "--work", str(tmp_path), "--area", "west-end"]) == 2


def test_scene_command_refuses_a_dsm_and_dem_on_different_grids(tmp_path: Path) -> None:
    work = WorkDir(tmp_path, CITY.id, "west-end")
    make_ingest(work.ingest)
    dem = Raster.load(work.ingest / "dem.npz")
    Raster(dem.x0 + 1.0, dem.y0, dem.cell, dem.data).save(work.ingest / "dem.npz")
    assert main(["scene", "--work", str(tmp_path), "--area", "west-end"]) == 2
