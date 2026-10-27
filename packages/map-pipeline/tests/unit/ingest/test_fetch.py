"""The fetch side, with a fake HTTP layer: no network here."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from qipu_map.geo.boxes import GeoBox
from qipu_map.geo.projection import LocalProjection
from qipu_map.ingest import lidar, opendata, overpass
from qipu_map.ingest.fetch import fetch_all, raw_name
from qipu_map.ingest.grid import LocalGrid, load_grid
from qipu_map.ingest.http import UrllibHttp, post_first
from qipu_map.ingest.raw import RawStore
from qipu_map.ingest.sources import VANCOUVER, sources_for
from tests.unit.ingest.helpers import FakeHttp, fc, line, sq

PROJ = LocalProjection(-123.1302, 49.2565)
BOX = GeoBox(49.28, -123.14, 49.281, -123.139)
TILES = {
    "features": [
        {"attributes": {"filename": "b.tif", "s3Url": "https://x/b.tif"}},
        {"attributes": {"filename": "a.tif", "s3Url": "https://x/a.tif"}},
    ]
}


def _answers() -> dict[str, Any]:
    return {
        "property-parcel-polygons": fc((sq(0, 0), {"tax_coord": "P1"}), (sq(2, 0), {"tax_coord": None})),
        "property-tax-report": [{"land_coordinate": "P1", "year_built": "1912"}],
        "shoreline-2002": fc((line((-500, 5), (500, 5)), {})),
        "/datasets/": fc(),
        "interpreter": {"elements": [{"type": "way", "id": 2}, {"type": "node", "id": 1}]},
        "FeatureServer": TILES,
    }


def _fake_reader(urls: list[str], grid: LocalGrid, projection: LocalProjection) -> Any:
    return np.full((grid.h, grid.w), float(len(urls)), np.float32)


def _fetch(store: RawStore, http: FakeHttp) -> list[str]:
    grid = LocalGrid(0.0, 3.0, 1.0, 3, 3)
    return fetch_all(store, sources=VANCOUVER, box=BOX, grid=grid, projection=PROJ, http=http, read_grid=_fake_reader)


def test_fetch_all_writes_every_raw_file_once(tmp_path: Path) -> None:
    store = RawStore(tmp_path, today=lambda: date(2026, 10, 26))
    http = FakeHttp(_answers())
    written = _fetch(store, http)
    assert set(written) == {raw_name(s) for s in VANCOUVER} | {"lidar_dsm.npz", "lidar_dem.npz"}
    assert store.retrieved() == dict.fromkeys(VANCOUVER, "2026-10-26")
    assert store.read_json("tax_roll.json") == [{"land_coordinate": "P1", "year_built": "1912"}]
    assert [e["type"] for e in store.read_json("osm.json")["elements"]] == ["node", "way"]
    assert load_grid(tmp_path / "lidar_dsm.npz").data[0, 0] == 2.0
    # the shoreline is cut to the box
    shore = store.read_json("shoreline.geojson")["features"][0]["geometry"]["coordinates"]
    assert min(x for x, _ in shore) >= BOX.west - 1e-12

    n_calls = len(http.calls)
    assert _fetch(store, http) == []
    assert len(http.calls) == n_calls  # the cache: nothing asked twice


def test_failed_fetch_leaves_no_file(tmp_path: Path) -> None:
    store = RawStore(tmp_path)

    def boom() -> bytes:
        raise OSError("down")

    with pytest.raises(OSError, match="down"):
        store.fetch_once("x", "x.json", boom)
    assert not store.has("x.json")
    assert store.retrieved() == {}


def test_opendata_asks_for_the_box_and_the_fields() -> None:
    http = FakeHttp({"": fc()})
    opendata.dataset_in_box(http, VANCOUVER["trees"], BOX)
    url, params = http.calls[0]
    assert url.endswith("/public-trees/exports/geojson")
    assert params["where"].startswith("intersects(geom, geom'POLYGON((-123.14 49.28,")
    assert params["select"] == "asset_id,genus_name,species_name,height_m,diameter_cm,geom"


def test_tax_roll_is_asked_in_chunks_of_parcels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opendata, "TAX_CHUNK", 2)
    http = FakeHttp({"": [{"land_coordinate": "z"}]})
    rows = json.loads(opendata.tax_roll(http, VANCOUVER["tax_roll"], ["c", "a", "b", "a"]))
    assert len(http.calls) == 2
    assert http.calls[0][1]["where"] == "report_year='2026' and land_coordinate in ('a','b')"
    assert rows == [{"land_coordinate": "z"}, {"land_coordinate": "z"}]


def test_overpass_query_and_mirror_fallback() -> None:
    q = overpass.query(BOX)
    assert q.startswith("[out:json]")
    assert 'way["natural"="coastline"](49.28,-123.14,49.281,-123.139);' in q
    http = FakeHttp({"overpass-api.de": OSError("busy"), "kumi": {"elements": []}})
    assert json.loads(overpass.fetch(http, VANCOUVER["osm"], BOX)) == {"elements": []}
    assert [u for u, _ in http.calls] == [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]


def test_every_mirror_down_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="every mirror"):
        post_first(FakeHttp({"": OSError("down")}), ["https://a", "https://b"], {})


def test_lidar_tile_index_is_sorted_by_file_name() -> None:
    http = FakeHttp({"FeatureServer/5/query": TILES})
    tiles = lidar.tile_index(http, VANCOUVER["lidar"], "dem", BOX)
    assert [t["filename"] for t in tiles] == ["a.tif", "b.tif"]
    assert http.calls[0][1]["where"] == "year=2025"


def test_no_tiles_is_an_error(tmp_path: Path) -> None:
    answers = _answers() | {"FeatureServer": {"features": []}}
    with pytest.raises(RuntimeError, match="no dsm tiles"):
        _fetch(RawStore(tmp_path), FakeHttp(answers))


def test_city_file_overrides_a_source() -> None:
    got = sources_for(
        {
            "tax_roll": {"params": {"report_year": "2025"}},
            "extra": {"name": "X", "url": "u", "licence": "l", "attribution": "a", "kind": "k"},
        }
    )
    assert got["tax_roll"].params["report_year"] == "2025"
    assert got["tax_roll"].params["dataset"] == "property-tax-report"
    assert got["extra"].name == "X"
    assert VANCOUVER["tax_roll"].params["report_year"] == "2026"


def test_only_https_sources_are_fetched() -> None:
    with pytest.raises(ValueError, match="https"):
        UrllibHttp(tries=1).get("http://example.org/data.json")
