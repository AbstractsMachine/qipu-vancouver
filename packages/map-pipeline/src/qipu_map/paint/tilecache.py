"""The painted-tile cache: one PNG per model call, named by the call's digest.

A digest covers every input pixel the call reads, the prompt, the seed, the noise key, the position and the painter's
recipe, so a hit is always safe to reuse and anything that changes the output changes the name. A re-run after a crash
or a partial fix paints only what is missing; a past year reuses every tile whose input region did not change from
another year (the folders listed in `also`). Writes go through a temporary file, so a killed run never leaves half a
tile behind.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from qipu_map.paint.backends import RGB


@dataclass
class TileCache:
    """The painted-tile cache: one PNG per model call in `folder`, named by digest; `also` lists other folders to copy a
    hit from."""

    folder: Path
    also: Sequence[Path] = ()
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)

    def path(self, digest: str) -> Path:
        return self.folder / f"{digest}.png"

    def get(self, digest: str) -> RGB | None:
        own = self.path(digest)
        if not own.is_file():
            found = next((p for p in (d / own.name for d in self.also) if p.is_file()), None)
            if found is None:
                self.misses += 1
                return None
            self.folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(found, own)
        self.hits += 1
        with Image.open(own) as im:
            return np.asarray(im.convert("RGB"), dtype=np.uint8)

    def put(self, digest: str, image: RGB) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / f".{digest}.tmp.png"
        Image.fromarray(image).save(tmp, compress_level=1)
        tmp.replace(self.path(digest))
