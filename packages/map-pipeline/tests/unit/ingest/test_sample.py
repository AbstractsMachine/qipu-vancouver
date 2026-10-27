"""`qipu-map ingest --raw` on the bundled West End sample: every layer comes out, twice the same."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qipu_map.cli import main
from qipu_map.model import Raster
from qipu_map.sample import SAMPLE_RAW

LAYERS = ("buildings", "streets", "trees", "parks", "water")


def _run(work: Path) -> Path:
    assert (
        main(["ingest", "--city", "vancouver", "--area", "west-end", "--work", str(work), "--raw", str(SAMPLE_RAW)])
        == 0
    )
    return work / "ca-vancouver" / "west-end" / "ingest"


def test_sample_produces_every_layer(tmp_path: Path) -> None:
    out = _run(tmp_path / "a")
    for name in LAYERS:
        fc = json.loads((out / f"{name}.geojson").read_text())
        assert len(fc["features"]) > 0, name
    kinds = {f["properties"]["kind"] for f in json.loads((out / "water.geojson").read_text())["features"]}
    assert "sea" in kinds
    dsm, dem = Raster.load(out / "dsm.npz"), Raster.load(out / "dem.npz")
    assert dsm.data.shape == dem.data.shape
    assert dsm.cell == 1.0
    assert np.nanmax(dsm.data - dem.data) > 30.0  # the West End's towers
    assert sorted(p.name for p in (out / "evidence").iterdir()) == ["napl1950.npz", "napl1959.npz"]
    sources = json.loads((out / "sources.json").read_text())
    assert {s["id"] for s in sources} >= {"footprints", "tax_roll", "osm", "lidar"}
    assert all(s["licence"] and s["attribution"] and s["retrieved"] and s["features"] > 0 for s in sources)


def test_sample_output_is_deterministic(tmp_path: Path) -> None:
    a, b = _run(tmp_path / "a"), _run(tmp_path / "b")
    for name in (*(f"{n}.geojson" for n in LAYERS), "dsm.npz", "dem.npz", "sources.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_second_run_is_skipped(tmp_path: Path) -> None:
    out = _run(tmp_path)
    before = (out / "buildings.geojson").stat().st_mtime_ns
    _run(tmp_path)
    assert (out / "buildings.geojson").stat().st_mtime_ns == before
