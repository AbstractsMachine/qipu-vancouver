from pathlib import Path

from qipu_map.cache import is_fresh, mark_done, stage_key


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_files_with_the_same_name_both_count(tmp_path: Path) -> None:
    past = _write(tmp_path / "scene" / "1950" / "scene.json", "a")
    today = _write(tmp_path / "scene" / "2026" / "scene.json", "b")
    before = stage_key("render", [past, today], {})
    past.write_text("changed")
    assert stage_key("render", [past, today], {}) != before


def test_the_key_follows_contents_and_params_not_order(tmp_path: Path) -> None:
    a, b = _write(tmp_path / "a.txt", "1"), _write(tmp_path / "b.txt", "2")
    assert stage_key("s", [a, b], {"x": 1}) == stage_key("s", [b, a], {"x": 1})
    assert stage_key("s", [a, b], {"x": 1}) != stage_key("s", [a, b], {"x": 2})


def test_a_single_input_is_keyed_by_its_name(tmp_path: Path) -> None:
    a = _write(tmp_path / "one" / "a.txt", "1")
    b = _write(tmp_path / "two" / "a.txt", "1")
    assert stage_key("s", [a], None) == stage_key("s", [b], None)


def test_stamps(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert not is_fresh(out, "k")
    mark_done(out, "k")
    assert is_fresh(out, "k")
    assert not is_fresh(out, "other")
