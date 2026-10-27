"""The era rules of a city, read from a small TOML file (`eras/rules/<city>.toml`).

Every rule says which of two kinds it is. A SOURCED rule takes a date from a dated record (the tax roll's year built, a
demolition permit, a bridge's opening day). A CONVENTION is a period choice made where no record speaks, and it must
never contradict one: it may fill an empty lot or guess a missing year, but it never removes a building a record says
stood, and never puts anything on a footprint where a recorded building stands.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).parent / "rules"


class Basis(StrEnum):
    SOURCED = "sourced"
    CONVENTION = "convention"


@dataclass(frozen=True)
class UndatedRule:
    """CONVENTION: a building with no year takes the median year of dated buildings near it.

    The first radius that finds any dated neighbour wins; the year is capped at `cap_year` (the footprints were traced
    that year, so the building stood by then), and with no neighbour at all it is `fallback_year`.
    """

    radii_m: tuple[float, ...]
    cap_year: int
    fallback_year: int
    tall_m: float
    tall_floor_year: int


@dataclass(frozen=True)
class ImprovedRule:
    """SOURCED year, CONVENTION reading: a building taller than `tall_m` whose roll gives a later big-improvement year
    stands from that year. One footprint can hold an old front and the tower added behind it (Tudor Manor: 1928 front,
    1989 tower); the roll dates the front, the improvement year dates the height."""

    tall_m: float


@dataclass(frozen=True)
class StandInRule:
    """CONVENTION: a period house on a lot that was built up before today's (newer) building stood there.

    A lot gets a stand-in when the building on it is younger than the year shown and either an air photo of the period
    shows the lot built up (`evidence_threshold`, for a building dated at least `evidence_margin_years` after the
    photo), or its street was already old: at least `min_neighbours` buildings within `radius_m`, `old_share` of them
    standing then, and today's building `gap_years` younger than their median. The stand-in takes the old neighbours'
    median year and height, and is replaced in the year today's building was built. A stand-in larger than
    `split_over_m2` (a tower's lot) is cut into houses on lots of `lot_width_m` by `lot_depth_m` (see `lots.py`).
    """

    radius_m: float
    min_neighbours: int
    old_share: float
    gap_years: int
    fallback_year: int
    default_height_m: float
    early_year: int
    early_max_height_m: float
    evidence_threshold: float
    evidence_margin_years: int
    max_overlap: float
    lot_width_m: float = 10.0
    lot_depth_m: float = 37.0
    split_over_m2: float = 300.0


@dataclass(frozen=True)
class Evidence:
    """A built-up mask read from one period's air photos or maps, and the era years it speaks for.

    The mask is a `model.Raster` in local metres (`<work>/ingest/evidence/<name>.npz`). A cell value is mapped linearly
    from `low` (nothing built) to `high` (fully built).
    """

    name: str
    photo_year: int
    first_year: int
    last_year: int
    low: float = 0.4
    high: float = 0.6
    source: str = ""

    def speaks_for(self, year: int) -> bool:
        return self.first_year <= year <= self.last_year


@dataclass(frozen=True)
class DatedFeature:
    """A date for features of today's data matched by id or name: bridges, rail lines, a record with a wrong year.

    For a street, `opened`/`closed` become its `year_opened`/`year_closed`; for a building, its
    `year_built`/`demolished`.
    """

    what: str
    layer: str
    basis: Basis
    source: str
    ids: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    opened: int | None = None
    closed: int | None = None

    def matches(self, feature_id: str, name: str | None) -> bool:
        if feature_id in self.ids:
            return True
        return name is not None and name.casefold() in {n.casefold() for n in self.names}


@dataclass(frozen=True)
class AreaOverride:
    """A polygon (lon, lat) where a period rule holds for the years [from_year, to_year).

    `water`: the place was still water (made land); buildings, streets and trees there are left out, unless a SOURCED
    record says a building stood. `drop_trees`, `drop_parks`: today's trees and parks did not exist yet. A positive
    `street_frontage_m` keeps a street only where a standing building is within that distance (a rail yard before the
    streets were laid). North False Creek before Expo 86, when it was rail yards, is such a case.
    """

    name: str
    polygon: tuple[tuple[float, float], ...]
    from_year: int
    to_year: int
    basis: Basis
    source: str
    water: bool = False
    drop_trees: bool = False
    drop_parks: bool = False
    street_frontage_m: float = 0.0

    def holds(self, year: int) -> bool:
        return self.from_year <= year < self.to_year


@dataclass(frozen=True)
class EraRules:
    city: str
    undated: UndatedRule
    improved: ImprovedRule
    standins: StandInRule
    undated_rail_in_past: bool
    evidence: tuple[Evidence, ...]
    dated: tuple[DatedFeature, ...]
    areas: tuple[AreaOverride, ...]

    def evidence_for(self, year: int) -> Evidence | None:
        return next((e for e in self.evidence if e.speaks_for(year)), None)


def load_rules(path: Path) -> EraRules:
    with path.open("rb") as f:
        return rules_from_dict(tomllib.load(f))


def rules_for_city(city_id: str, override: Path | None = None) -> EraRules:
    """The rules file for a city id (`ca/vancouver` reads `rules/vancouver.toml`), or the file given."""
    return load_rules(override or RULES_DIR / f"{city_id.rsplit('/', 1)[-1]}.toml")


def rules_from_dict(raw: dict[str, Any]) -> EraRules:
    u, s = raw["undated"], raw["standins"]
    return EraRules(
        city=raw["city"],
        undated=UndatedRule(
            tuple(float(r) for r in u["radii_m"]),
            int(u["cap_year"]),
            int(u["fallback_year"]),
            float(u["tall_m"]),
            int(u["tall_floor_year"]),
        ),
        improved=ImprovedRule(float(raw["improved"]["tall_m"])),
        standins=StandInRule(**{k: v for k, v in s.items() if k not in ("basis", "why")}),
        undated_rail_in_past=bool(raw.get("streets", {}).get("undated_rail_in_past", True)),
        evidence=tuple(Evidence(**e) for e in raw.get("evidence", ())),
        dated=tuple(_dated(d) for d in raw.get("dated", ())),
        areas=tuple(_area(a) for a in raw.get("areas", ())),
    )


def _dated(d: dict[str, Any]) -> DatedFeature:
    if d["layer"] not in ("streets", "buildings"):
        raise ValueError(f"dated feature {d['what']!r}: layer must be streets or buildings, got {d['layer']!r}")
    return DatedFeature(
        what=d["what"],
        layer=d["layer"],
        basis=Basis(d["basis"]),
        source=d["source"],
        ids=tuple(str(i) for i in d.get("ids", ())),
        names=tuple(d.get("names", ())),
        opened=d.get("opened"),
        closed=d.get("closed"),
    )


def _area(a: dict[str, Any]) -> AreaOverride:
    return AreaOverride(
        name=a["name"],
        polygon=tuple((float(p[0]), float(p[1])) for p in a["polygon"]),
        from_year=int(a.get("from_year", -10_000)),
        to_year=int(a["to_year"]),
        basis=Basis(a["basis"]),
        source=a["source"],
        water=bool(a.get("water", False)),
        drop_trees=bool(a.get("drop_trees", False)),
        drop_parks=bool(a.get("drop_parks", False)),
        street_frontage_m=float(a.get("street_frontage_m", 0.0)),
    )
