from pathlib import Path

from qipu_map.files import read_json, write_atomic, write_json


def test_write_json_is_sorted_and_ends_with_a_newline(tmp_path: Path) -> None:
    path = tmp_path / "a" / "x.json"
    write_json(path, {"b": 1, "a": "–"})
    assert path.read_text(encoding="utf-8") == '{\n "a": "–",\n "b": 1\n}\n'
    write_json(path, {"b": [1, 2], "a": None}, compact=True)
    assert path.read_text() == '{"a":null,"b":[1,2]}\n'
    assert read_json(path) == {"a": None, "b": [1, 2]}


def test_write_atomic_leaves_no_temporary_file(tmp_path: Path) -> None:
    write_atomic(tmp_path / "t.bin", b"abc")
    assert [p.name for p in tmp_path.iterdir()] == ["t.bin"]
    assert (tmp_path / "t.bin").read_bytes() == b"abc"
