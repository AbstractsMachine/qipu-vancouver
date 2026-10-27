"""Which prompt a tile gets, and its text.

The key comes from what the render's class pass shows in the tile, never from a hand-drawn area: an area key painted
houses on a meadow that sat inside a houses area. The rules:

- a tile that is almost all water is not painted at all; the render's water is the map's water;
- a mostly open tile (buildings at most 8 %, open ground at least 60 %) gets a key that names no building, roof, wall,
  street or water: any of those words, even negated, makes the model paint the thing (it planted roof gardens from
  "no roof gardens");
- an open tile with a lot of sea gets the shore key, which names the sea, or the model paints streets over it;
- a building tile is `towers` when tall facades fill much of it (a stand-in for a hand-drawn downtown), else
  `base`; either gets the rail clause where the render shows track;
- a past year swaps the towers clause for a period clause and the open keys for a period open-ground text.

The texts live in `prompts/<city>_*.txt`, one fragment per file, so a prompt change is a reviewed text diff. Every
tile's cache key includes its full prompt text, so editing a file repaints exactly the tiles that use it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass as C

PROMPTS_DIR = Path(__file__).parent / "prompts"
LEAD = "Turn this 3D render into a real aerial photograph"

WATER_SKIP = 0.95
BLD_MAX, OPEN_MIN = 0.08, 0.60
SHORE_WATER, SAND_MIN, WOODS_TREE = 0.25, 0.06, 0.55
RAIL_MIN = 0.01
TOWER_WALL = 0.15
EARLY_BEFORE = 1960


class Key(StrEnum):
    """The prompt a tile gets, chosen from what its class pass shows."""

    BASE = "base"
    TOWERS = "towers"
    MEADOW = "meadow"
    WOODS = "woods"
    BEACH = "beach"
    SHORE = "shore"


@dataclass(frozen=True)
class Content:
    """Shares of a tile's pixels, from the class pass."""

    water: float
    building: float
    open: float
    tree: float
    sand: float
    rail: float
    wall: float

    @classmethod
    def measure(cls, classes: NDArray[np.uint8]) -> Content:
        n = float(classes.size)

        def share(*ids: C) -> float:
            return float(np.isin(classes, [int(i) for i in ids]).sum()) / n

        return cls(
            water=share(C.WATER),
            building=share(C.ROOF, C.WALL),
            open=share(C.GROUND, C.GRASS, C.TREE, C.SAND, C.WATER),
            tree=share(C.TREE),
            sand=share(C.SAND),
            rail=share(C.RAIL),
            wall=share(C.WALL),
        )


@dataclass(frozen=True)
class Choice:
    """A tile's prompt key and whether it gets the rail clause."""

    key: Key
    rail: bool


def choose(c: Content) -> Choice | None:
    """The tile's prompt key, or None for a water tile that keeps the render."""
    if c.water >= WATER_SKIP:
        return None
    if c.building <= BLD_MAX and c.open >= OPEN_MIN:
        if c.water >= SHORE_WATER:
            return Choice(Key.SHORE, False)
        if c.sand >= SAND_MIN:
            return Choice(Key.BEACH, False)
        if c.tree >= WOODS_TREE:
            return Choice(Key.WOODS, False)
        return Choice(Key.MEADOW, False)
    return Choice(Key.TOWERS if c.wall >= TOWER_WALL else Key.BASE, c.rail >= RAIL_MIN)


def decades(year: int) -> str:
    return "the 1960s" if year < 1975 else "the 1960s and 1970s"


@dataclass(frozen=True)
class PromptSet:
    """A city's prompt fragments, read from `prompts/<city>_<name>.txt`."""

    city: str
    parts: dict[str, str]
    anchor_lead: str

    @classmethod
    def load(cls, city: str, folder: Path = PROMPTS_DIR) -> PromptSet:
        parts = {p.stem.removeprefix(f"{city}_"): p.read_text().strip() for p in sorted(folder.glob(f"{city}_*.txt"))}
        if "base" not in parts:
            raise FileNotFoundError(f"no prompts for {city!r} in {folder}")
        return cls(city, parts, (folder / "anchor.txt").read_text().strip())

    def text(self, choice: Choice, year: int, today: int) -> str:
        """The full prompt for a tile painted for `year`."""
        p, past = self.parts, year < today
        if choice.key is Key.SHORE:
            return p["shore"]
        if choice.key in (Key.MEADOW, Key.WOODS, Key.BEACH):
            if past:
                return _join(p["open"], p["period_open"].format(year=year))
            return _join(p["open"], p[f"kind_{choice.key}"], "" if choice.key is Key.BEACH else p["lush"])
        clause = ""
        if choice.key is Key.TOWERS:
            era = "early" if year < EARLY_BEFORE else "postwar"
            clause = p[f"period_{era}_towers"].format(year=year, decades=decades(year)) if past else p["kind_towers"]
        tail = (p["rail"], p["keep"]) if choice.rail else (p["green"],)
        return _join(p["base"], clause, *tail)

    def anchored(self, prompt: str) -> str:
        """The second pass's prompt: image 1 is the soft first-pass painting, image 2 the render, whose geometry
        wins."""
        if not prompt.startswith(LEAD):
            raise ValueError("a prompt must start with the lead sentence to be anchored")
        return self.anchor_lead + prompt[len(LEAD) :]


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p)
