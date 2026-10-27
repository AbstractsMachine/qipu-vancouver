import hashlib
from pathlib import Path

import pytest

from qipu_map.hashing import file_digest, short_id, stable_fraction, stable_seed, value_digest


def test_file_digest_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"x" * 3_000_000)
    assert file_digest(path) == hashlib.sha256(path.read_bytes()).hexdigest()
    assert file_digest(path, "md5") == hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def test_value_digest_ignores_key_order() -> None:
    assert value_digest({"a": 1, "b": [1, 2]}) == value_digest({"b": [1, 2], "a": 1})
    assert value_digest({"a": 1}) != value_digest({"a": 2})


def test_stable_seed_is_the_sha1_prefix() -> None:
    hexdigest = hashlib.sha1(b"7:512,1024", usedforsecurity=False).hexdigest()
    assert stable_seed("7:512,1024") == int(hexdigest[:8], 16)
    assert stable_seed("7:512,1024", bits=60) == int(hexdigest[:15], 16)
    with pytest.raises(ValueError, match="bits"):
        stable_seed("x", bits=0)


def test_stable_fraction_is_fixed_and_spread() -> None:
    values = [stable_fraction(f"b{i}") for i in range(1000)]
    assert all(0.0 <= v < 1.0 for v in values)
    assert 0.4 < sum(values) / len(values) < 0.6
    assert stable_fraction("b1") == stable_fraction("b1")


def test_short_id() -> None:
    assert short_id(b"abc") == hashlib.sha1(b"abc", usedforsecurity=False).hexdigest()[:12]
    assert len(short_id(b"abc", chars=6)) == 6
