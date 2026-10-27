"""The painters behind one small interface.

A painter takes a request (reference images, a prompt, a seed, where the tile is in the world and which noise key to
use) and returns one image. The real one is `DiffusersKlein` (in `klein.py`, needs a CUDA GPU and the `paint` extra);
the two here are deterministic stand-ins for tests and CI:

- `Identity` returns its last reference image (for the second pass, the render tile), so a painted canvas equals the
  pre-toned render and every other step of the stage can be checked against it.
- `Replay` returns images recorded earlier, looked up by the request's digest: a GPU run's tiles can be replayed on a
  laptop to re-quilt or re-check them without a GPU.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from PIL import Image

RGB = NDArray[np.uint8]


@dataclass(frozen=True)
class Request:
    """One model call. `level` 8 is the half-resolution first pass, 9 the full-resolution pass; (x, y) is the output's
    top-left in world pixels of that level, which places its noise in the world field."""

    images: tuple[RGB, ...]
    prompt: str
    seed: int
    noise_key: str
    level: int
    x: int
    y: int
    size: int

    def digest(self, recipe: str) -> str:
        """The cache key: every input pixel, the prompt, seed, noise, position and the recipe."""
        h = hashlib.sha256()
        h.update(recipe.encode())
        h.update(f"|{self.prompt}|{self.seed}|{self.noise_key}|{self.level}|{self.x},{self.y}|{self.size}|".encode())
        for im in self.images:
            h.update(f"{im.shape}".encode())
            h.update(np.ascontiguousarray(im).tobytes())
        return h.hexdigest()


class Painter(Protocol):
    """What the paint stage needs from a painter: a name, a recipe string for the cache key, and a call that returns one
    image per request."""

    @property
    def name(self) -> str: ...

    @property
    def recipe(self) -> str:
        """What makes this painter's output what it is (model, steps, guidance). Part of every tile's cache key."""
        ...

    def paint(self, request: Request) -> RGB: ...


def resize(image: RGB, size: int) -> RGB:
    """The square image resized to `size` pixels (Lanczos), or the same image if it already is."""
    if image.shape[0] == size and image.shape[1] == size:
        return image
    out: RGB = np.asarray(Image.fromarray(image).resize((size, size), Image.Resampling.LANCZOS), dtype=np.uint8)
    return out


class Identity:
    name = "identity"
    recipe = "identity"

    def paint(self, request: Request) -> RGB:
        return resize(request.images[-1], request.size)


class Replay:
    """Recorded outputs in a folder, one `<digest>.png` per request: a GPU run's tile cache. `recipe` is the recorded
    painter's, so the digests match."""

    name = "replay"

    def __init__(self, folder: Path, recipe: str) -> None:
        self.folder = folder
        self.recipe = recipe

    def paint(self, request: Request) -> RGB:
        path = self.folder / f"{request.digest(self.recipe)}.png"
        if not path.is_file():
            raise FileNotFoundError(f"no recorded output for this request: {path.name}")
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"), dtype=np.uint8)


def model_recipe(model: str, steps: int, guidance: float) -> str:
    """The recipe string of a model call, part of every tile's cache key."""
    return f"{model}|steps={steps}|guidance={guidance}|bf16"


def make_painter(name: str, model: str, steps: int, guidance: float, replay_dir: Path | None = None) -> Painter:
    """The painter called `name`: identity, replay (needs `replay_dir`) or diffusers. Raises `ValueError` for any other
    name."""
    if name == "identity":
        return Identity()
    if name == "replay":
        if replay_dir is None:
            raise ValueError("the replay painter needs a folder of recorded outputs")
        return Replay(replay_dir, recipe=model_recipe(model, steps, guidance))
    if name == "diffusers":
        from qipu_map.paint.klein import DiffusersKlein  # noqa: PLC0415 (torch is an optional extra)

        return DiffusersKlein(model=model, steps=steps, guidance=guidance)
    raise ValueError(f"unknown painter {name!r}: identity, replay or diffusers")
