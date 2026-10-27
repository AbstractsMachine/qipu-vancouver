"""Hashes the pipeline relies on: file and value digests for the caches, and stable draws.

A stable draw is a "random" choice fixed by a key (a building's id, a tile's position), so it is the same in every
run, on every machine and in every year. Each draw keeps the hash it was made with: changing one reshuffles every
building's roof, colour or tile seed, so these functions say which hash they use and should not be swapped.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20


def file_digest(path: Path, algorithm: str = "sha256") -> str:
    """The hex digest of a file's bytes, read in chunks. MD5 is what S3 stores as an object's ETag."""
    h = hashlib.new(algorithm, usedforsecurity=False)
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def value_digest(value: Any) -> str:
    """The SHA-256 of a JSON-serialisable value, with dict keys sorted so equal values hash alike."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def stable_seed(key: str, bits: int = 32) -> int:
    """The first `bits` bits of the key's SHA-1, as an integer. At 32 bits this is the paint grid's tile seed."""
    if not 0 < bits <= 160:
        raise ValueError(f"bits must be in 1..160, got {bits}")
    return int.from_bytes(hashlib.sha1(key.encode(), usedforsecurity=False).digest(), "big") >> (160 - bits)


def stable_fraction(key: str) -> float:
    """A number in [0, 1) fixed by the key: the first 64 bits of its SHA-256 over 2^64."""
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def short_id(data: bytes, chars: int = 12) -> str:
    """A short hex id for something its source does not number (a street segment): the start of its SHA-1."""
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()[:chars]
