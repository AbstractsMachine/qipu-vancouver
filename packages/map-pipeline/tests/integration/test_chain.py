"""The stages run together on a corner of the West End sample: the CPU chain from raw open data to a published release.

The area is the south-west corner of the sample (houses, towers, the park and English Bay), with one past year, so the
whole chain takes a few seconds. `make sample` runs the full sample the same way.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from qipu_map.cli import main
from qipu_map.model import Scene
from qipu_map.sample import SAMPLE_RAW

PAST, TODAY = 1950, 2026


CITY_FILE = Path(__file__).parent / "fixtures" / "corner.toml"


def chain_after_ingest(work: Path, out: Path) -> list[list[str]]:
    where = ["--city", str(CITY_FILE), "--area", "corner", "--work", str(work)]
    return [
        ["scene", *where],
        ["eras", "scene", *where],
        ["render", *where, "--backend", "preview"],
        ["paint", *where, "--backend", "identity", "--year", str(TODAY)],
        ["paint", *where, "--backend", "identity", "--year", str(PAST)],
        ["eras", "layers", *where],
        ["tiles", *where],
        ["publish", *where, "--release", "test", "--to", str(out)],
    ]


@pytest.fixture(scope="module")
def release(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("chain")
    ingest = [
        "ingest",
        "--city",
        str(CITY_FILE),
        "--area",
        "corner",
        "--work",
        str(tmp / "work"),
        "--raw",
        str(SAMPLE_RAW),
    ]
    for argv in [ingest, *chain_after_ingest(tmp / "work", tmp / "out")]:
        assert main(argv) == 0, argv
    return tmp


def _base(release: Path) -> Path:
    return release / "work" / "ca-vancouver" / "corner"


def test_the_past_scene_holds_only_what_stood_then(release: Path) -> None:
    today = Scene.load(_base(release) / "scene" / str(TODAY) / "scene.json")
    past = Scene.load(_base(release) / "scene" / str(PAST) / "scene.json")
    assert today.buildings
    assert past.buildings
    assert all(b.year_built is None or b.year_built <= PAST for b in past.buildings if b.year_source != "convention")
    newer = [b for b in today.buildings if b.year_built and b.year_built > PAST]
    assert newer, "the corner has towers built after 1950"
    assert not {b.id for b in newer} & {b.id for b in past.buildings}


def test_every_year_shares_one_canvas(release: Path) -> None:
    plans = [
        json.loads((_base(release) / "render" / str(y) / "frames.json").read_text())["canvas"] for y in (PAST, TODAY)
    ]
    assert plans[0] == plans[1]


def test_the_painted_canvas_matches_the_render(release: Path) -> None:
    canvas = json.loads((_base(release) / "render" / str(TODAY) / "frames.json").read_text())["canvas"]
    with Image.open(_base(release) / "paint" / str(TODAY) / "canvas.png") as im:
        assert im.size == (canvas["width"], canvas["height"])


def test_the_release_follows_the_tile_format(release: Path) -> None:
    root = release / "out" / "test"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["format"] == "qipu-tiles/1"
    assert manifest["today"]["year"] == TODAY
    assert [y["year"] for y in manifest["years"]] == [PAST]
    assert [(s["from"], s["to"]) for s in manifest["switch"]] == [(PAST, TODAY)]
    zmax = manifest["today"]["zmax"]
    tile = root / manifest["today"]["path"].format(z=zmax, x=0, y=0)
    with Image.open(tile) as im:
        assert im.size == (512, 512)
    assert (root / manifest["ground"]).is_file()


def test_date_maps_say_when_buildings_appear(release: Path) -> None:
    root = release / "out" / "test"
    manifest = json.loads((root / "manifest.json").read_text())
    switch = manifest["switch"][0]
    z = switch["zmax"]
    have = manifest["switch"][0]["have"][str(z)]
    tile = root / switch["path"].format(z=z, x=have["x0"], y=have["y0"])
    rgb = np.asarray(Image.open(tile).convert("RGB")).astype(np.int64)
    n = rgb[..., 0] * 256 + rgb[..., 1]
    dated = n[n != 65535]
    assert dated.size, "some pixels change between 1950 and today"
    years = 1800 + dated / 100
    assert years.min() >= PAST
    assert years.max() <= TODAY + 1


def test_a_second_run_changes_nothing(release: Path) -> None:
    where = ["--city", str(CITY_FILE), "--area", "corner", "--work", str(release / "work")]
    before = (_base(release) / "scene" / str(TODAY) / "scene.json").stat().st_mtime_ns
    assert main(["scene", *where]) == 0
    assert (_base(release) / "scene" / str(TODAY) / "scene.json").stat().st_mtime_ns == before


def test_a_changed_input_reaches_every_later_stage(release: Path, tmp_path: Path) -> None:
    shutil.copytree(release / "work", tmp_path / "work")
    base = tmp_path / "work" / "ca-vancouver" / "corner"
    outputs = [
        base / "scene" / str(TODAY) / "scene.json",
        base / "scene" / str(PAST) / "scene.json",
        base / "render" / str(TODAY) / "frames.json",
        base / "render" / str(PAST) / "frames.json",
        base / "paint" / str(TODAY) / "canvas.png",
        base / "paint" / str(PAST) / "canvas.png",
        base / "eras" / str(PAST) / "layer.png",
        base / "eras" / "switch" / f"{PAST}-{TODAY}" / "dates.png",
        base / "tiles" / "today" / "pyramid.json",
        base / "tiles" / "manifest.json",
    ]
    before = {p: p.stat().st_mtime_ns for p in outputs}
    old_manifest = json.loads((release / "out" / "test" / "manifest.json").read_text())

    # The corner's tallest building is taken out of the open data: every stage after ingest must notice.
    today = Scene.load(base / "scene" / str(TODAY) / "scene.json")
    tallest = max(today.buildings, key=lambda b: b.height_m).id
    layer = base / "ingest" / "buildings.geojson"
    data = json.loads(layer.read_text())
    data["features"] = [f for f in data["features"] if f["properties"]["id"] != tallest]
    layer.write_text(json.dumps(data))
    for argv in chain_after_ingest(tmp_path / "work", tmp_path / "out"):
        assert main(argv) == 0, argv

    unchanged = [p.relative_to(base).as_posix() for p in outputs if p.stat().st_mtime_ns == before[p]]
    assert unchanged == [], unchanged
    manifest = json.loads((tmp_path / "out" / "test" / "manifest.json").read_text())
    assert manifest["today"]["v"] != old_manifest["today"]["v"]
