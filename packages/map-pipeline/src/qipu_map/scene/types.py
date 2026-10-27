"""Which kind of building each footprint is: a character house, a Vancouver Special, a point tower and so on.

The type picks the roof pitch and, in the renderer and the painter, the look. It is decided from what the open data
says: the year built, the measured height, the footprint's size and shape, the roof the LiDAR saw and the use
(a zoning district from the tax roll, or an OpenStreetMap building tag). The bands are the ones the Vancouver map
was made with; they are a convention, written down so that each decision can be traced.

`RULES` is the table: the first rule that matches decides, and each rule carries the reason it exists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from qipu_map.model import BuildingType, RoofForm


class Use(StrEnum):
    HOUSE = "house"
    MULTI = "multi"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    CIVIC = "civic"
    ACCESSORY = "accessory"
    UNKNOWN = "unknown"


# Zoning district prefixes (City of Vancouver zoning by-law) and OSM building tags, to a use.
_ZONES: tuple[tuple[tuple[str, ...], Use], ...] = (
    (("RS-", "RT-", "R1-", "R2-", "R3-", "R4-", "R5-", "RA-", "FSD", "FM-"), Use.HOUSE),
    (("RM-", "FM-1"), Use.MULTI),
    (("C-", "FC-", "HA-", "DD", "DEOD", "CWD", "BCPED"), Use.COMMERCIAL),
    (("I-", "M-", "IC-"), Use.INDUSTRIAL),
)
_TAGS: dict[str, Use] = {
    **dict.fromkeys(("house", "detached", "semidetached_house", "bungalow"), Use.HOUSE),
    **dict.fromkeys(("apartments", "residential", "terrace", "townhouse", "dormitory"), Use.MULTI),
    **dict.fromkeys(("commercial", "retail", "office", "supermarket", "shop", "mall"), Use.COMMERCIAL),
    **dict.fromkeys(("industrial", "warehouse", "manufacture", "factory", "hangar"), Use.INDUSTRIAL),
    **dict.fromkeys(
        (
            "school",
            "church",
            "civic",
            "public",
            "hospital",
            "university",
            "college",
            "hotel",
            "government",
            "fire_station",
            "library",
            "museum",
            "train_station",
            "community_centre",
        ),
        Use.CIVIC,
    ),
    **dict.fromkeys(("garage", "garages", "shed", "carport", "hut"), Use.ACCESSORY),
}


def use_of(value: str | None) -> Use:
    """A zoning district or an OSM building tag, to a use; anything else (CD-1, "yes", nothing) is UNKNOWN."""
    if not value:
        return Use.UNKNOWN
    v = value.strip()
    if v.lower() in _TAGS:
        return _TAGS[v.lower()]
    for prefixes, use in _ZONES:
        if v.upper().startswith(prefixes):
            return use
    return Use.UNKNOWN


STEEP_PITCH_DEG = 35.0  # roofs this steep are the pre-war character houses' roofs
PREWAR_GUESS = 1925  # any year before 1946 types an undated steep roof as a character house
POSTWAR_GUESS = 1975  # a flat or low roof says post-war: a year of the 1965-85 boxes and walk-ups


@dataclass(frozen=True)
class Facts:
    """What the rules look at, for one building."""

    year: int | None
    height_m: float
    top_m: float  # the LiDAR's 90th percentile: the tower, when the median reads a podium (else the height)
    area_m2: float
    fill: float  # footprint area over its minimum-area rectangle's: 1 for a box
    roof: RoofForm | None  # what the LiDAR saw; None when it could not tell
    pitch_deg: float
    use: Use
    beside_bigger: bool  # a bigger building stands within a lot's depth: this one is in its back yard

    @property
    def pitched(self) -> bool:
        return self.roof in (RoofForm.GABLE, RoofForm.HIP)

    @property
    def year_or_guess(self) -> int:
        """The year, or a guess from the roof when there is none. The guess only picks the type; it is never written out
        as the year built."""
        if self.year is not None:
            return self.year
        return PREWAR_GUESS if self.pitched and self.pitch_deg >= STEEP_PITCH_DEG else POSTWAR_GUESS


@dataclass(frozen=True)
class Rule:
    name: str
    reason: str
    applies: Callable[[Facts], bool]
    kind: Callable[[Facts], BuildingType]


def _house(f: Facts) -> BuildingType:
    y = f.year_or_guess
    if y < 1946:
        return BuildingType.CHARACTER_HOUSE
    if 1965 <= y < 1986 and _special_box(f):
        return BuildingType.VANCOUVER_SPECIAL
    return BuildingType.MODERN_HOUSE


def _special_box(f: Facts) -> bool:
    low_roof = f.roof in (None, RoofForm.FLAT) or f.pitch_deg <= 30
    return 5.5 <= f.height_m <= 10 and f.area_m2 >= 100 and f.fill >= 0.84 and low_roof


def _multi(f: Facts) -> BuildingType:
    y, h = f.year_or_guess, f.height_m
    if y < 1946:
        return BuildingType.WALK_UP if (not f.pitched and h >= 8) else BuildingType.CHARACTER_HOUSE
    if y < 1980:
        return BuildingType.MID_RISE if h >= 17 else BuildingType.WALK_UP if h >= 7.5 else BuildingType.MODERN_HOUSE
    if h < 10.5 and (f.pitched or (y >= 2006 and f.area_m2 < 600)):
        return BuildingType.ROW_HOUSE
    if h < 22:
        return BuildingType.WALK_UP if y < 2006 else BuildingType.MID_RISE
    return BuildingType.POINT_TOWER


def _is(kind: BuildingType) -> Callable[[Facts], BuildingType]:
    return lambda _f: kind


RULES: tuple[Rule, ...] = (
    Rule(
        "tower on a podium",
        "one outline holds a tower over a low base: the median reads the base, so the height alone would call it low",
        lambda f: f.top_m >= 32 and f.height_m < 0.6 * f.top_m,
        _is(BuildingType.PODIUM_TOWER),
    ),
    Rule(
        "tower",
        "32 m is about ten storeys: nothing else in the city is that tall",
        lambda f: f.height_m >= 32,
        _is(BuildingType.POINT_TOWER),
    ),
    Rule(
        "industrial",
        "industrial zones and tags, over 150 m² so a shed in a works yard stays a shed",
        lambda f: f.use is Use.INDUSTRIAL and f.area_m2 >= 150,
        _is(BuildingType.INDUSTRIAL),
    ),
    Rule(
        "outbuilding",
        "under 30 m² or under 3.2 m is a garage or a shed, whatever the zoning says",
        lambda f: f.use is Use.ACCESSORY or f.area_m2 < 30 or f.height_m < 3.2,
        _is(BuildingType.SHED),
    ),
    Rule(
        "laneway house",
        "a small building behind a bigger one is a laneway house when it has a storey and a half, else a garage",
        lambda f: f.area_m2 < 90 and f.height_m <= 8.5 and f.beside_bigger,
        lambda f: BuildingType.LANEWAY_HOUSE if f.height_m >= 4.8 else BuildingType.SHED,
    ),
    Rule(
        "civic",
        "schools, churches, halls, hospitals and hotels by their tag",
        lambda f: f.use is Use.CIVIC,
        _is(BuildingType.CIVIC),
    ),
    Rule(
        "big low building in a house zone",
        "in the single-family zones a footprint of 700 m² or more is a school, church or hall",
        lambda f: f.use is Use.HOUSE and f.area_m2 >= 700,
        _is(BuildingType.CIVIC),
    ),
    Rule(
        "house",
        "house zones and tags, and any low unzoned footprint under 450 m²: by period, character house before 1946, a "
        "Vancouver Special for a 1965-85 two-storey box with a low roof, else a modern house",
        lambda f: f.use is Use.HOUSE or (f.use is Use.UNKNOWN and f.area_m2 < 450 and f.height_m < 12),
        _house,
    ),
    Rule(
        "shops and offices",
        "commercial zones: a low block is a shop or office building, a taller one a mid-rise",
        lambda f: f.use is Use.COMMERCIAL,
        lambda f: BuildingType.COMMERCIAL if f.height_m < 12 else BuildingType.MID_RISE,
    ),
    Rule(
        "apartments",
        "everything else is housing by period and height: pre-war blocks, the 1950s-70s walk-ups, then row houses, "
        "low-rises, mid-rises and towers",
        lambda f: True,
        _multi,
    ),
)


def classify(f: Facts) -> tuple[BuildingType, str]:
    """The building's type and the name of the rule that decided it."""
    for rule in RULES:
        if rule.applies(f):
            return rule.kind(f), rule.name
    raise AssertionError("the last rule matches everything")


# A type's height when neither the LiDAR nor OpenStreetMap gives one, and the use's height before the type is known.
DEFAULT_HEIGHT_M: dict[BuildingType, float] = {
    BuildingType.CHARACTER_HOUSE: 8.5,
    BuildingType.VANCOUVER_SPECIAL: 7.5,
    BuildingType.MODERN_HOUSE: 8.0,
    BuildingType.LANEWAY_HOUSE: 5.5,
    BuildingType.ROW_HOUSE: 9.0,
    BuildingType.WALK_UP: 11.0,
    BuildingType.MID_RISE: 20.0,
    BuildingType.POINT_TOWER: 60.0,
    BuildingType.PODIUM_TOWER: 10.0,  # the podium; its tower takes the LiDAR's top
    BuildingType.COMMERCIAL: 8.0,
    BuildingType.INDUSTRIAL: 8.0,
    BuildingType.CIVIC: 10.0,
    BuildingType.SHED: 3.0,
}
USE_HEIGHT_M: dict[Use, float] = {
    Use.HOUSE: 8.0,
    Use.MULTI: 11.0,
    Use.COMMERCIAL: 8.0,
    Use.INDUSTRIAL: 8.0,
    Use.CIVIC: 10.0,
    Use.ACCESSORY: 3.0,
    Use.UNKNOWN: 8.0,
}

# The roof a type gets when the LiDAR could not tell: the most common roof of that type.
DEFAULT_ROOF: dict[BuildingType, RoofForm] = {
    BuildingType.CHARACTER_HOUSE: RoofForm.GABLE,
    BuildingType.VANCOUVER_SPECIAL: RoofForm.GABLE,
    BuildingType.MODERN_HOUSE: RoofForm.HIP,
    BuildingType.LANEWAY_HOUSE: RoofForm.GABLE,
    BuildingType.ROW_HOUSE: RoofForm.GABLE,
    BuildingType.SHED: RoofForm.FLAT,
}
