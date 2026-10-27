"""The scene: what stands where, how tall, and since when.

Coordinates are local metres (see `geo.projection`): x east, y north, z up. Rings are open (the last point is not a copy
of the first) and outer rings run counter-clockwise. A scene is written as one JSON file; rasters (the terrain) are
written next to it as `.npz` and referenced by file name.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from qipu_map.files import read_json, write_json
from qipu_map.geo.boxes import WorldBox

Point = tuple[float, float]
Ring = tuple[Point, ...]

SCENE_FORMAT = "qipu-scene/1"


def signed_area(ring: Ring) -> float:
    """The ring's area, positive when it runs counter-clockwise (the shoelace formula)."""
    return 0.5 * sum(a[0] * c[1] - c[0] * a[1] for a, c in zip(ring, ring[1:] + ring[:1], strict=True))


def ccw(ring: Ring) -> Ring:
    """The ring running counter-clockwise, as outer rings do here."""
    return ring if signed_area(ring) > 0 else tuple(reversed(ring))


class RoofForm(StrEnum):
    FLAT = "flat"
    GABLE = "gable"
    HIP = "hip"


class YearSource(StrEnum):
    """Where a year comes from. SOURCED years are read from a dated record; CONVENTION years are a rule's choice."""

    TAX_ROLL = "tax_roll"
    PERMIT = "permit"
    OSM = "osm"
    HISTORICAL = "historical"
    CONVENTION = "convention"


class BuildingType(StrEnum):
    CHARACTER_HOUSE = "character_house"
    VANCOUVER_SPECIAL = "vancouver_special"
    MODERN_HOUSE = "modern_house"
    LANEWAY_HOUSE = "laneway_house"
    ROW_HOUSE = "row_house"
    WALK_UP = "walk_up"
    MID_RISE = "mid_rise"
    POINT_TOWER = "point_tower"
    PODIUM_TOWER = "podium_tower"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    CIVIC = "civic"
    SHED = "shed"


class StreetKind(StrEnum):
    ARTERIAL = "arterial"
    RESIDENTIAL = "residential"
    LANE = "lane"
    PATH = "path"
    RAIL = "rail"


class TreeForm(StrEnum):
    BROADLEAF = "broadleaf"
    CONIFER = "conifer"
    PALM = "palm"


@dataclass(frozen=True)
class Polygon:
    outer: Ring
    holes: tuple[Ring, ...] = ()


@dataclass(frozen=True)
class Building:
    id: str
    footprint: Ring
    ground_m: float
    height_m: float
    roof: RoofForm
    kind: BuildingType
    year_built: int | None
    year_source: YearSource
    demolished: int | None = None
    storeys: int | None = None
    year_improved: int | None = None

    def stands_in(self, year: float) -> bool:
        """True if the building stood at any time in `year`. Undated buildings are taken as always there."""
        built = self.year_built is None or self.year_built <= year
        gone = self.demolished is not None and self.demolished <= year
        return built and not gone


@dataclass(frozen=True)
class Street:
    id: str
    line: tuple[Point, ...]
    width_m: float
    kind: StreetKind
    name: str | None = None
    year_opened: int | None = None
    year_closed: int | None = None


@dataclass(frozen=True)
class Tree:
    id: str
    x: float
    y: float
    height_m: float
    crown_m: float
    form: TreeForm
    genus: str | None = None
    year_planted: int | None = None


@dataclass(frozen=True)
class Park:
    id: str
    shape: Polygon
    name: str | None = None


@dataclass(frozen=True)
class Raster:
    """A north-up grid: cell (0, 0) is the north-west one, its top-left corner is (x0, y0), rows go south."""

    x0: float
    y0: float
    cell: float
    data: NDArray[np.float32]

    def sample(self, x: ArrayLike, y: ArrayLike) -> NDArray[np.float64]:
        """Bilinear values at the points (x, y), clamped to the grid's edge."""
        h, w = self.data.shape
        fx = np.clip((np.asarray(x, dtype=np.float64) - self.x0) / self.cell - 0.5, 0.0, w - 1.0)
        fy = np.clip((self.y0 - np.asarray(y, dtype=np.float64)) / self.cell - 0.5, 0.0, h - 1.0)
        j0, i0 = fx.astype(np.int64), fy.astype(np.int64)
        j1, i1 = np.minimum(j0 + 1, w - 1), np.minimum(i0 + 1, h - 1)
        tx, ty = fx - j0, fy - i0
        d = self.data.astype(np.float64)
        top = d[i0, j0] * (1 - tx) + d[i0, j1] * tx
        bottom = d[i1, j0] * (1 - tx) + d[i1, j1] * tx
        out: NDArray[np.float64] = top * (1 - ty) + bottom * ty
        return out

    def same_grid(self, other: Raster) -> bool:
        """True when both rasters have the same corner, cell size and shape, so cell (i, j) is one place in both."""
        return (self.x0, self.y0, self.cell, self.data.shape) == (other.x0, other.y0, other.cell, other.data.shape)

    def value_at(self, x: float, y: float) -> float:
        """`sample` at one point."""
        return float(self.sample(x, y))

    def crop(self, box: tuple[float, float, float, float], margin: float = 0.0) -> Raster:
        """The cells that touch the box (x0, y0, x1, y1) grown by `margin` metres, on the same grid; at least one
        cell."""
        h, w = self.data.shape
        j0 = min(max(math.floor((box[0] - margin - self.x0) / self.cell), 0), w - 1)
        j1 = min(max(math.ceil((box[2] + margin - self.x0) / self.cell), j0 + 1), w)
        i0 = min(max(math.floor((self.y0 - box[3] - margin) / self.cell), 0), h - 1)
        i1 = min(max(math.ceil((self.y0 - box[1] + margin) / self.cell), i0 + 1), h)
        data = np.ascontiguousarray(self.data[i0:i1, j0:j1], dtype=np.float32)
        return Raster(self.x0 + j0 * self.cell, self.y0 - i0 * self.cell, self.cell, data)

    def save(self, path: Path) -> None:
        np.savez_compressed(path, data=self.data, x0=self.x0, y0=self.y0, cell=self.cell)

    @classmethod
    def load(cls, path: Path) -> Raster:
        with np.load(path) as z:
            return cls(float(z["x0"]), float(z["y0"]), float(z["cell"]), z["data"].astype(np.float32))


@dataclass(frozen=True)
class Scene:
    """Everything the renderer draws for one area and one year."""

    city: str
    area: str
    year: int
    box: WorldBox
    buildings: tuple[Building, ...]
    streets: tuple[Street, ...]
    trees: tuple[Tree, ...]
    parks: tuple[Park, ...]
    water: tuple[Polygon, ...]
    land: tuple[Polygon, ...]
    terrain_file: str
    notes: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["format"] = SCENE_FORMAT
        return d

    def save(self, path: Path) -> None:
        write_json(path, self.to_json(), compact=True)

    @classmethod
    def load(cls, path: Path) -> Scene:
        return scene_from_json(read_json(path))


def _ring(r: list[list[float]]) -> Ring:
    return tuple((float(p[0]), float(p[1])) for p in r)


def _polygon(d: dict[str, Any]) -> Polygon:
    return Polygon(_ring(d["outer"]), tuple(_ring(h) for h in d.get("holes", ())))


def scene_from_json(d: dict[str, Any]) -> Scene:
    if d.get("format") != SCENE_FORMAT:
        raise ValueError(f"not a {SCENE_FORMAT} file (format={d.get('format')!r})")
    return Scene(
        city=d["city"],
        area=d["area"],
        year=int(d["year"]),
        box=WorldBox(*(float(v) for v in d["box"])),
        buildings=tuple(
            Building(
                id=b["id"],
                footprint=_ring(b["footprint"]),
                ground_m=b["ground_m"],
                height_m=b["height_m"],
                roof=RoofForm(b["roof"]),
                kind=BuildingType(b["kind"]),
                year_built=b["year_built"],
                year_source=YearSource(b["year_source"]),
                demolished=b.get("demolished"),
                storeys=b.get("storeys"),
                year_improved=b.get("year_improved"),
            )
            for b in d["buildings"]
        ),
        streets=tuple(
            Street(
                id=s["id"],
                line=_ring(s["line"]),
                width_m=s["width_m"],
                kind=StreetKind(s["kind"]),
                name=s.get("name"),
                year_opened=s.get("year_opened"),
                year_closed=s.get("year_closed"),
            )
            for s in d["streets"]
        ),
        trees=tuple(
            Tree(
                id=t["id"],
                x=t["x"],
                y=t["y"],
                height_m=t["height_m"],
                crown_m=t["crown_m"],
                form=TreeForm(t["form"]),
                genus=t.get("genus"),
                year_planted=t.get("year_planted"),
            )
            for t in d["trees"]
        ),
        parks=tuple(Park(id=p["id"], shape=_polygon(p["shape"]), name=p.get("name")) for p in d["parks"]),
        water=tuple(_polygon(w) for w in d["water"]),
        land=tuple(_polygon(p) for p in d["land"]),
        terrain_file=d["terrain_file"],
        notes=d.get("notes", {}),
    )
