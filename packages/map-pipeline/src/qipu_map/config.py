"""City and area settings, read from a TOML file.

A city file (see `cities/vancouver.toml`) holds what does not change between runs: the projection origin, the camera,
the eras, the painter's recipe and the named areas. Where work files go is not part of it: that comes from the command
line or the `QIPU_MAP_WORK` environment variable, so the same city file works on a laptop, a GPU box and in CI.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qipu_map.errors import StageError
from qipu_map.geo.boxes import GeoBox

WORK_ENV = "QIPU_MAP_WORK"
CITIES_DIR = Path(__file__).parent / "cities"


@dataclass(frozen=True)
class Projection:
    """The local projection: x = (lon - lon0) * metres_per_degree * cos(lat0) east, y = (lat - lat0) * metres_per_degree
    north."""

    lon0: float
    lat0: float
    metres_per_degree: float = 111_320.0


@dataclass(frozen=True)
class Camera:
    """A fixed orthographic camera: it looks toward `azimuth_deg` (0 = north), tilted `elevation_deg` below the
    horizon."""

    azimuth_deg: float
    elevation_deg: float
    metres_per_px: float
    tile_size: int = 512


@dataclass(frozen=True)
class Sun:
    azimuth_deg: float
    elevation_deg: float


@dataclass(frozen=True)
class Area:
    """A named box (south, west, north, east in degrees) that a run covers."""

    name: str
    bbox: GeoBox

    def __post_init__(self) -> None:
        south, west, north, east = self.bbox
        if not (south < north and west < east):
            raise ValueError(f"area {self.name}: bbox must be (south, west, north, east), got {self.bbox}")


@dataclass(frozen=True)
class Eras:
    """Past years to render. `today` is the year the open data describes."""

    today: int
    years: tuple[int, ...]
    footprint_survey_year: int

    def __post_init__(self) -> None:
        if any(y >= self.today for y in self.years):
            raise ValueError(f"every era year must be before today ({self.today}): {self.years}")
        if list(self.years) != sorted(set(self.years)):
            raise ValueError(f"era years must be increasing and unique: {self.years}")


@dataclass(frozen=True)
class Paint:
    """The painter's recipe. Changing any field changes every tile's cache key."""

    model: str
    tile_px: int
    stride_px: int
    steps: int
    guidance: float
    seed: int

    def __post_init__(self) -> None:
        if not 0 < self.stride_px <= self.tile_px:
            raise ValueError("stride_px must be in (0, tile_px]")


@dataclass(frozen=True)
class Publish:
    """Where tiles go. `bucket_url` is s3://bucket/prefix (any S3-compatible store) or a local folder."""

    bucket_url: str
    public_url: str
    endpoint_env: str = "QIPU_MAP_S3_ENDPOINT"
    cache_control: str = "public, max-age=300"
    manifest_cache_control: str = "public, max-age=60"


@dataclass(frozen=True)
class City:
    """One city's settings as read from its TOML file; `area` looks up a named area."""

    id: str
    name: str
    projection: Projection
    camera: Camera
    sun: Sun
    eras: Eras
    paint: Paint
    publish: Publish
    areas: dict[str, Area]
    attribution: tuple[str, ...]
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def area(self, name: str) -> Area:
        try:
            return self.areas[name]
        except KeyError:
            raise StageError(f"{self.id} has no area {name!r}; known: {', '.join(sorted(self.areas))}") from None


def load_city(name_or_path: str | Path) -> City:
    """Load a city by name (a file in the package's `cities/`) or by path. Raises `StageError` if it is missing or
    malformed."""
    path = Path(name_or_path)
    if not path.suffix:
        path = CITIES_DIR / f"{name_or_path}.toml"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in CITIES_DIR.glob("*.toml")))
        raise StageError(f"no city file {path}; the bundled cities are: {known}")
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
        return city_from_dict(raw)
    except tomllib.TOMLDecodeError as e:
        raise StageError(f"{path}: not valid TOML: {e}") from e
    except KeyError as e:
        raise StageError(f"{path}: missing {e.args[0]!r}") from e
    except (TypeError, ValueError) as e:  # an unknown or missing key in a section, or a value the section refuses
        raise StageError(f"{path}: {e}") from e


def city_from_dict(raw: dict[str, Any]) -> City:
    c = raw["city"]
    return City(
        id=c["id"],
        name=c["name"],
        projection=Projection(**raw["projection"]),
        camera=Camera(**raw["camera"]),
        sun=Sun(**raw["sun"]),
        eras=Eras(
            today=raw["eras"]["today"],
            years=tuple(raw["eras"]["years"]),
            footprint_survey_year=raw["eras"]["footprint_survey_year"],
        ),
        paint=Paint(**raw["paint"]),
        publish=Publish(**raw["publish"]),
        areas={k: Area(name=k, bbox=GeoBox(*v["bbox"])) for k, v in raw.get("areas", {}).items()},
        attribution=tuple(c.get("attribution", ())),
        sources=raw.get("sources", {}),
    )


def work_root(cli_value: str | Path | None = None) -> Path:
    """The folder that holds every stage's outputs: the --work option, else $QIPU_MAP_WORK, else ./work."""
    if cli_value is not None:
        return Path(cli_value)
    return Path(os.environ.get(WORK_ENV, "work"))
