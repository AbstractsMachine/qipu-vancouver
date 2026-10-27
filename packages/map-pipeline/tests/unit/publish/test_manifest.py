from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from qipu_map.config import City
from qipu_map.geo.camera import Canvas, ObliqueCamera
from qipu_map.model import Raster
from qipu_map.publish.ground import ground_grid
from qipu_map.publish.manifest import build_manifest, find_layers, read_layer, switch_pairs
from qipu_map.render.frames import load_plan
from qipu_map.tiles.have import unpack_have
from tests.unit.publish.conftest import CANVAS, make_work


def test_manifest_has_every_field_of_the_contract(tmp_path: Path, city: City) -> None:
    work = make_work(tmp_path)
    m = build_manifest(city, "west-end", "r20261026", CANVAS, find_layers(work.tiles), ground="ground.json")
    assert set(m) == {
        "format", "city", "area", "release", "tile_size", "canvas", "camera", "projection",
        "world_to_px", "today", "years", "switch", "ground", "attribution",
    }  # fmt: skip
    assert m["format"] == "qipu-tiles/1"
    assert m["city"] == "ca/vancouver"
    assert m["release"] == "r20261026"
    assert m["canvas"] == {"width": 40, "height": 30, "metres_per_px": 0.25, "zmax": 2}
    assert m["camera"] == {"azimuth_deg": 0.0, "elevation_deg": 30.709}
    assert m["projection"] == {
        "kind": "local-equirectangular",
        "lon0": -123.1302,
        "lat0": 49.2565,
        "metres_per_degree": 111320.0,
    }
    assert m["today"]["year"] == 2026
    assert m["today"]["path"] == "today/{z}/{x}/{y}.webp"
    assert m["today"]["zmax"] == 2
    assert [y["year"] for y in m["years"]] == [1950, 1972]
    assert all(y["zmax"] == 1 and y["path"] == f"years/{y['year']}/{{z}}/{{x}}/{{y}}.webp" for y in m["years"])
    assert [(s["from"], s["to"]) for s in m["switch"]] == [(1950, 1972), (1972, 2026)]
    assert m["switch"][0]["path"] == "switch/1950-1972/{z}/{x}/{y}.png"
    assert m["attribution"] == list(city.attribution)
    for layer in [m["today"], *m["years"], *m["switch"]]:
        assert len(layer["v"]) == 8
        assert set(layer) >= {"path", "zmax", "v", "have"}
        assert not layer["path"].startswith("/")


def test_have_lists_exactly_the_tiles_on_disk(tmp_path: Path, city: City) -> None:
    work = make_work(tmp_path)
    m = build_manifest(city, "west-end", "r1", CANVAS, find_layers(work.tiles), ground=None)
    assert "ground" not in m
    for z, have in m["today"]["have"].items():
        on_disk = {(int(p.parent.name), int(p.stem)) for p in (work.today_tiles() / z).glob("*/*.webp")}
        assert unpack_have(have) == on_disk
    assert (0, 0) not in unpack_have(m["today"]["have"]["2"])


def test_world_to_px_is_the_canvas_affine(tmp_path: Path, city: City) -> None:
    work = make_work(tmp_path)
    m = build_manifest(city, "west-end", "r1", CANVAS, find_layers(work.tiles), ground=None)
    canvas = Canvas(ObliqueCamera(0.0, 30.709, 0.25), -100.0, 250.0, 40, 30)
    w = np.array(m["world_to_px"])
    for xyz in [(0.0, 0.0, 0.0), (12.0, 400.0, 30.0)]:
        assert w @ np.array([*xyz, 1.0]) == pytest.approx(canvas.to_px(*xyz), abs=1e-4)


def test_version_changes_with_a_tile_and_not_otherwise(tmp_path: Path) -> None:
    work = make_work(tmp_path, years=(), switch=False)
    before = read_layer(work.tiles, "today").version
    assert read_layer(work.tiles, "today").version == before
    tile = next(work.today_tiles().glob("2/*/*.webp"))
    tile.write_bytes(tile.read_bytes() + b"\0")
    assert read_layer(work.tiles, "today").version != before


def test_manifest_refuses_layers_that_do_not_fit(tmp_path: Path, city: City) -> None:
    work = make_work(tmp_path, switch=False)
    layers = find_layers(work.tiles)
    with pytest.raises(ValueError, match="date maps"):
        build_manifest(city, "west-end", "r1", CANVAS, layers, ground=None)
    with pytest.raises(ValueError, match="re-run"):
        build_manifest(city, "west-end", "r1", replace(CANVAS, width=400), layers, ground=None)


def test_a_release_without_years_needs_no_date_maps(tmp_path: Path, city: City) -> None:
    work = make_work(tmp_path, years=(), switch=False)
    m = build_manifest(city, "west-end", "r1", CANVAS, find_layers(work.tiles), ground=None)
    assert m["years"] == []
    assert m["switch"] == []


def test_find_layers_needs_today(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="tiles"):
        find_layers(tmp_path)


def test_switch_pairs_end_at_today() -> None:
    assert switch_pairs([1972, 1930, 1950], 2026) == [(1930, 1950), (1950, 1972), (1972, 2026)]


def test_canvas_info_reads_frames_json(tmp_path: Path) -> None:
    work = make_work(tmp_path, years=(), switch=False)
    assert load_plan(work.render(2026)).canvas == CANVAS


def test_ground_grid_averages_blocks_in_decimetres() -> None:
    data = np.zeros((60, 70), dtype=np.float32)
    data[:25, :25] = 10.0
    data[59, 69] = np.nan
    g = ground_grid(Raster(x0=-60.0, y0=80.0, cell=1.0, data=data))
    assert (g["x0"], g["y0"], g["cell"], g["cols"], g["rows"]) == (-60.0, 80.0, 25.0, 3, 3)
    assert len(g["decimetres"]) == 9
    assert g["decimetres"][0] == 100
    assert g["decimetres"][1] == 0
    assert g["decimetres"][8] == 0


def test_ground_grid_matches_the_terrain_where_sampled() -> None:
    yy, xx = np.mgrid[0:100, 0:100].astype(np.float32)
    terrain = Raster(x0=0.0, y0=100.0, cell=1.0, data=(xx * 0.1 + yy * 0.2).astype(np.float32))
    g = ground_grid(terrain)
    grid = Raster(
        g["x0"],
        g["y0"],
        g["cell"],
        (np.array(g["decimetres"], dtype=np.float32).reshape(g["rows"], g["cols"]) / 10).astype(np.float32),
    )
    for x, y in [(30.0, 60.0), (55.0, 40.0)]:
        assert grid.sample(x, y) == pytest.approx(terrain.sample(x, y), abs=0.1)
