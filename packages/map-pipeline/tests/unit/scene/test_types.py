"""One test per type rule, each on a building like the ones the rule was written for."""

from __future__ import annotations

from dataclasses import replace

import pytest

from qipu_map.model import BuildingType, RoofForm
from qipu_map.scene.types import DEFAULT_HEIGHT_M, RULES, Facts, Use, classify, use_of

# A 1912 Kitsilano house: 8 x 14 m, a steep front gable, on an RT-7 lot.
KITS_HOUSE = Facts(
    year=1912,
    height_m=9.0,
    top_m=9.5,
    area_m2=112.0,
    fill=0.97,
    roof=RoofForm.GABLE,
    pitch_deg=42.0,
    use=Use.HOUSE,
    beside_bigger=False,
)


def kind(f: Facts) -> BuildingType:
    return classify(f)[0]


def test_every_rule_has_a_reason() -> None:
    assert all(r.reason and r.name for r in RULES)
    assert len({r.name for r in RULES}) == len(RULES)


def test_tower_on_a_podium() -> None:
    """The LiDAR's median reads the podium of a Yaletown tower; its 90th percentile reaches the tower."""
    f = replace(KITS_HOUSE, year=2008, height_m=12.0, top_m=95.0, area_m2=2400.0, use=Use.UNKNOWN, roof=RoofForm.FLAT)
    assert classify(f) == (BuildingType.PODIUM_TOWER, "tower on a podium")


def test_tower() -> None:
    """A 1960s West End point tower, 19 storeys."""
    f = replace(KITS_HOUSE, year=1968, height_m=58.0, top_m=60.0, area_m2=620.0, use=Use.MULTI, roof=RoofForm.FLAT)
    assert kind(f) is BuildingType.POINT_TOWER


def test_industrial() -> None:
    f = replace(KITS_HOUSE, year=1955, height_m=8.0, area_m2=1800.0, use=Use.INDUSTRIAL, roof=RoofForm.FLAT)
    assert kind(f) is BuildingType.INDUSTRIAL


def test_a_small_building_in_an_industrial_zone_is_a_shed() -> None:
    f = replace(KITS_HOUSE, height_m=3.0, area_m2=60.0, use=Use.INDUSTRIAL)
    assert kind(f) is BuildingType.SHED


def test_outbuilding_by_size_or_tag() -> None:
    assert kind(replace(KITS_HOUSE, area_m2=22.0, height_m=3.0)) is BuildingType.SHED
    assert kind(replace(KITS_HOUSE, use=Use.ACCESSORY, area_m2=40.0)) is BuildingType.SHED


def test_laneway_house_and_garage_behind_a_house() -> None:
    laneway = replace(KITS_HOUSE, year=2014, height_m=6.0, area_m2=60.0, beside_bigger=True)
    assert kind(laneway) is BuildingType.LANEWAY_HOUSE
    assert kind(replace(laneway, height_m=3.8)) is BuildingType.SHED


def test_civic_by_tag() -> None:
    f = replace(KITS_HOUSE, year=1928, height_m=14.0, area_m2=900.0, use=Use.CIVIC)
    assert kind(f) is BuildingType.CIVIC


def test_big_footprint_in_a_house_zone_is_civic() -> None:
    """A church on an RS-1 lot: the zoning says house, the size says otherwise."""
    f = replace(KITS_HOUSE, height_m=11.0, area_m2=850.0)
    assert classify(f) == (BuildingType.CIVIC, "big low building in a house zone")


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (1912, BuildingType.CHARACTER_HOUSE),
        (1955, BuildingType.MODERN_HOUSE),
        (1995, BuildingType.MODERN_HOUSE),
        (2019, BuildingType.MODERN_HOUSE),
    ],
)
def test_house_by_period(year: int, expected: BuildingType) -> None:
    assert kind(replace(KITS_HOUSE, year=year)) is expected


def test_vancouver_special() -> None:
    """1977, two storeys, a near-rectangular box of 180 m², a low gable."""
    special = replace(KITS_HOUSE, year=1977, height_m=7.5, area_m2=180.0, fill=0.92, pitch_deg=18.0)
    assert kind(special) is BuildingType.VANCOUVER_SPECIAL
    assert kind(replace(special, fill=0.7)) is BuildingType.MODERN_HOUSE  # an L-shaped house is not a Special
    assert kind(replace(special, height_m=4.5)) is BuildingType.MODERN_HOUSE  # a bungalow


def test_undated_house_takes_its_period_from_the_roof() -> None:
    assert kind(replace(KITS_HOUSE, year=None)) is BuildingType.CHARACTER_HOUSE
    # a low roof means 1975, and a two-storey box of that year is a Special
    assert kind(replace(KITS_HOUSE, year=None, pitch_deg=20.0)) is BuildingType.VANCOUVER_SPECIAL


def test_unzoned_small_building_is_a_house() -> None:
    assert kind(replace(KITS_HOUSE, use=Use.UNKNOWN)) is BuildingType.CHARACTER_HOUSE


def test_shops_and_offices() -> None:
    shop = replace(KITS_HOUSE, year=1925, height_m=7.0, area_m2=400.0, use=Use.COMMERCIAL, roof=RoofForm.FLAT)
    assert kind(shop) is BuildingType.COMMERCIAL
    assert kind(replace(shop, year=1975, height_m=20.0)) is BuildingType.MID_RISE


@pytest.mark.parametrize(
    ("year", "height", "roof", "area", "expected"),
    [
        (1910, 12.0, RoofForm.FLAT, 500.0, BuildingType.WALK_UP),  # a brick apartment block
        (1910, 9.0, RoofForm.GABLE, 300.0, BuildingType.CHARACTER_HOUSE),  # a house split into suites
        (1962, 11.0, RoofForm.FLAT, 600.0, BuildingType.WALK_UP),  # a West End three-storey walk-up
        (1962, 20.0, RoofForm.FLAT, 600.0, BuildingType.MID_RISE),
        (1962, 6.0, RoofForm.FLAT, 500.0, BuildingType.MODERN_HOUSE),
        (1992, 9.0, RoofForm.GABLE, 500.0, BuildingType.ROW_HOUSE),
        (1992, 14.0, RoofForm.HIP, 900.0, BuildingType.WALK_UP),  # a leaky-condo low-rise
        (2012, 9.0, RoofForm.FLAT, 400.0, BuildingType.ROW_HOUSE),
        (2012, 18.0, RoofForm.FLAT, 1200.0, BuildingType.MID_RISE),
        (2012, 28.0, RoofForm.FLAT, 900.0, BuildingType.POINT_TOWER),
    ],
)
def test_apartments(year: int, height: float, roof: RoofForm, area: float, expected: BuildingType) -> None:
    f = replace(
        KITS_HOUSE, year=year, height_m=height, top_m=height, roof=roof, area_m2=area, use=Use.MULTI, pitch_deg=30.0
    )
    assert kind(f) is expected


@pytest.mark.parametrize(
    ("value", "use"),
    [
        ("RS-1", Use.HOUSE),
        ("RT-7", Use.HOUSE),
        ("RM-5A", Use.MULTI),
        ("C-2", Use.COMMERCIAL),
        ("HA-1A", Use.COMMERCIAL),
        ("I-2", Use.INDUSTRIAL),
        ("CD-1 (123)", Use.UNKNOWN),
        ("apartments", Use.MULTI),
        ("church", Use.CIVIC),
        ("Garage", Use.ACCESSORY),
        ("yes", Use.UNKNOWN),
        (None, Use.UNKNOWN),
    ],
)
def test_use_from_zoning_or_tag(value: str | None, use: Use) -> None:
    assert use_of(value) is use


def test_every_type_has_a_default_height() -> None:
    assert set(DEFAULT_HEIGHT_M) == set(BuildingType)
