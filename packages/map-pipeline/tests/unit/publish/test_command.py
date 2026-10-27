import json
import shutil
from pathlib import Path

import pytest

from qipu_map.cli import main
from qipu_map.paths import WorkDir
from tests.unit.publish.conftest import make_work


def _city_file(tmp_path: Path) -> Path:
    src = (Path(__file__).parents[3] / "src/qipu_map/cities/vancouver.toml").read_text()
    src = src.replace("tile_size = 512", "tile_size = 16").replace(
        "years = [1930, 1950, 1972, 1982]", "years = [1950, 1972]"
    )
    path = tmp_path / "city.toml"
    path.write_text(src)
    return path


def _publish(tmp_path: Path, *extra: str) -> int:
    city = _city_file(tmp_path)
    return main(
        [
            "publish",
            "--city",
            str(city),
            "--area",
            "west-end",
            "--work",
            str(tmp_path / "work"),
            "--release",
            "r1",
            *extra,
        ]
    )


def test_publish_to_a_folder_writes_the_release(tmp_path: Path) -> None:
    work: WorkDir = make_work(tmp_path / "work")
    site = tmp_path / "site"
    assert _publish(tmp_path, "--to", str(site)) == 0
    manifest = json.loads((site / "r1" / "manifest.json").read_text())
    assert manifest["release"] == "r1"
    assert manifest["ground"] == "ground.json"
    assert json.loads((site / "r1" / "ground.json").read_text())["decimetres"][0] == 123
    for layer in [manifest["today"], *manifest["years"], *manifest["switch"]]:
        assert (site / "r1" / layer["path"].format(z=0, x=0, y=0)).is_file()
    assert not list(site.rglob("pyramid.json"))
    assert not list(site.rglob(".stamp"))
    assert work.manifest.read_text() == (site / "r1" / "manifest.json").read_text()


def test_dry_run_lists_changes_and_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_work(tmp_path / "work")
    site = tmp_path / "site"
    assert _publish(tmp_path, "--to", str(site), "--dry-run") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1].startswith("manifest.json")
    assert not site.exists()
    _publish(tmp_path, "--to", str(site))
    capsys.readouterr()
    _publish(tmp_path, "--to", str(site), "--dry-run")
    assert capsys.readouterr().out == ""


def test_publish_explains_what_is_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_work(tmp_path / "work")
    shutil.rmtree(WorkDir(tmp_path / "work", "ca/vancouver", "west-end").today_tiles())
    assert _publish(tmp_path, "--to", str(tmp_path / "site")) == 2
    assert "qipu-map tiles" in capsys.readouterr().err
    assert (
        main(
            [
                "publish",
                "--city",
                "vancouver",
                "--area",
                "west-end",
                "--work",
                str(tmp_path),
                "--release",
                "../x",
                "--to",
                "x",
            ]
        )
        == 2
    )
    assert "release name" in capsys.readouterr().err


def test_publish_has_no_default_target_or_area(tmp_path: Path) -> None:
    for argv in (["--to", "x"], ["--city", "vancouver", "--to", "x"], ["--city", "vancouver", "--area", "west-end"]):
        with pytest.raises(SystemExit):
            main(["publish", *argv, "--work", str(tmp_path), "--release", "r1"])
