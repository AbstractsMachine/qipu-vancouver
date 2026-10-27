"""GeoJSON writing, OSM element reading, the HTTP retry loop and the windowed LiDAR read."""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely

from qipu_map.geo.projection import LocalProjection
from qipu_map.ingest import http as http_mod
from qipu_map.ingest.grid import LocalGrid
from qipu_map.ingest.normalise import geojson, osm
from tests.unit.ingest.helpers import line, sq, way


def test_layer_is_sorted_rounded_and_carries_its_id(tmp_path: Path) -> None:
    feats = [
        geojson.Feature("b", shapely.Point(-123.123456789, 49.1), {"k": 1}),
        geojson.Feature("a", shapely.Point(0.0, 0.0), {}),
    ]
    assert geojson.write_layer(tmp_path / "x.geojson", feats) == 2
    fc = json.loads((tmp_path / "x.geojson").read_text())
    assert [f["id"] for f in fc["features"]] == ["a", "b"]
    assert fc["features"][1]["geometry"]["coordinates"] == [-123.1234568, 49.1]
    assert fc["features"][1]["properties"] == {"id": "b", "k": 1}


def test_duplicate_ids_are_refused() -> None:
    f = geojson.Feature("a", shapely.Point(0, 0), {})
    with pytest.raises(ValueError, match="duplicate"):
        geojson.collection([f, f])


def test_shape_id_ignores_sub_centimetre_noise() -> None:
    a = geojson.shape_id("s", shapely.LineString([(1.0, 2.0), (3.0, 4.0)]))
    b = geojson.shape_id("s", shapely.LineString([(1.00000001, 2.0), (3.0, 4.0)]))
    assert a == b
    assert a.startswith("s-")


def test_relation_outer_minus_inner() -> None:
    outer, inner = sq(0, 0, 10, 10), sq(3, 3, 2, 2)
    rel = {
        "type": "relation",
        "id": 5,
        "tags": {"building": "yes"},
        "members": [
            {"type": "way", "role": "outer", "geometry": way(1, outer)["geometry"]},
            {"type": "way", "role": "inner", "geometry": way(2, inner)["geometry"]},
            {"type": "node", "role": "", "lon": 0, "lat": 0},
        ],
    }
    g = osm.area_shape(rel)
    assert g is not None
    assert abs(g.area - (outer.area - inner.area)) < 1e-15
    assert osm.osm_id(rel) == "osm-r5"
    assert osm.area_shape({"type": "relation", "id": 6, "members": []}) is None


def test_open_way_is_no_area() -> None:
    assert osm.area_shape(way(1, line((0, 0), (1, 0), (1, 1)))) is None


@pytest.mark.parametrize(
    ("v", "m"), [("12", 12.0), ("12,5 m", 12.5), ("100'", 30.48), ("10 feet", 3.048), ("tall", None), (None, None)]
)
def test_metres(v: str | None, m: float | None) -> None:
    got = osm.metres(v)
    assert got == pytest.approx(m) if m is not None else got is None


def test_year_of_reads_the_first_dated_tag() -> None:
    assert osm.year_of({"start_date": "~1912", "opening_date": "1999"}) == 1912
    assert osm.year_of({"start_date": "early", "construction_date": "2017-03"}) == 2017
    assert osm.year_of({"name": "1900 Club"}) is None


def test_elements_skip_untagged_and_sort() -> None:
    raw = {
        "elements": [
            {"type": "way", "id": 2, "tags": {"a": "b"}},
            {"type": "node", "id": 1},
            {"type": "way", "id": 1, "tags": {"a": "b"}},
        ]
    }
    assert [e["id"] for e in osm.elements(raw)] == [1, 2]


class _Resp(io.BytesIO):
    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *a: object) -> None:
        return None


def test_urllib_http_retries_then_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def urlopen(req: Any, timeout: float) -> _Resp:
        calls.append(req)
        if len(calls) < 2:
            raise OSError("reset")
        return _Resp(b"ok")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    h = http_mod.UrllibHttp(tries=3, pause_s=0.0)
    assert h.get("https://x/y", {"a": "1 2"}) == b"ok"
    assert calls[0].full_url == "https://x/y?a=1+2"
    assert h.post("https://x/p", {"data": "q"}) == b"ok"
    assert calls[-1].data == b"data=q"


def test_urllib_http_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(req: Any, timeout: float) -> _Resp:
        raise OSError("down")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(OSError, match="down"):
        http_mod.UrllibHttp(tries=2, pause_s=0.0).get("https://x")


def _status_once(monkeypatch: pytest.MonkeyPatch, code: int) -> list[str]:
    calls: list[str] = []

    def urlopen(req: Any, timeout: float) -> _Resp:
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, code, "x", Message(), None)
        return _Resp(b"ok")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return calls


@pytest.mark.parametrize("code", [500, 503, 408, 429])
def test_urllib_http_retries_a_transient_status(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    calls = _status_once(monkeypatch, code)
    assert http_mod.UrllibHttp(tries=3, pause_s=0.0).get("https://x/y") == b"ok"
    assert len(calls) == 2


@pytest.mark.parametrize("code", [400, 403, 404, 410])
def test_urllib_http_does_not_retry_a_client_error(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    calls = _status_once(monkeypatch, code)
    with pytest.raises(urllib.error.HTTPError):
        http_mod.UrllibHttp(tries=3, pause_s=0.0).get("https://x/y")
    assert len(calls) == 1


def test_read_grid_resamples_a_utm_tile_onto_local_metres(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio", reason="needs the lidar extra")
    pyproj = pytest.importorskip("pyproj", reason="needs the lidar extra")
    from qipu_map.ingest.lidar import read_grid  # noqa: PLC0415 (after the skip: the module is fine, the test needs rasterio)

    proj = LocalProjection(-123.1302, 49.2565)
    grid = LocalGrid(-600.0, 2600.0, 1.0, 4, 3)
    lon, lat = proj.to_lonlat(-600.0, 2600.0)
    e0, n0 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:26910", always_xy=True).transform(lon, lat)
    e0, n0 = float(np.floor(e0)) - 5, float(np.ceil(n0)) + 5
    # a tile whose value is its column index: sampled values must step by about one per metre east
    data = np.tile(np.arange(20, dtype=np.float32), (20, 1))
    data[:, 0] = -32767.0
    path = tmp_path / "t.tif"
    transform = rasterio.transform.from_origin(e0, n0, 1.0, 1.0)
    profile = {
        "driver": "GTiff",
        "width": 20,
        "height": 20,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:26910",
        "transform": transform,
        "nodata": -32767.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    out = read_grid([str(path)], grid, proj)
    assert out.shape == (3, 4)
    assert np.isfinite(out).all()
    steps = np.diff(out, axis=1)
    assert ((steps >= 0) & (steps <= 2)).all()
    assert steps.sum() > 0
