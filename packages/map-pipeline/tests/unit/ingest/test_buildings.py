from __future__ import annotations

import pytest

from qipu_map.ingest.normalise import buildings as b
from qipu_map.ingest.normalise.geojson import Feature
from tests.unit.ingest.helpers import fc, sq, way

M2 = (111_320.0 * 0.6526738) * 111_320.0  # m² per square degree at Vancouver


def _index(roll: list[dict[str, str]]) -> b.ParcelIndex:
    parcels = fc(
        (sq(0, 0, 10, 10), {"tax_coord": "A"}), (sq(10, 0, 10, 10), {"tax_coord": "B"}), (sq(20, 0, 10, 10), {})
    )
    return b.ParcelIndex(parcels, b.parcels_from_roll(roll))


def test_roll_takes_the_most_common_valid_year_of_a_parcel() -> None:
    rows: list[dict[str, str | None]] = [
        {"land_coordinate": "A", "year_built": "1972", "zoning_district": "RM-5"},
        {"land_coordinate": "A", "year_built": "1968", "zoning_district": "RM-5"},
        {"land_coordinate": "B", "year_built": "1800", "zoning_district": None},
        {"land_coordinate": "C", "year_built": "", "zoning_district": "C-5"},
        {"land_coordinate": "", "year_built": "1900"},
    ]
    roll = b.parcels_from_roll(rows)
    # a tie goes to the oldest year, as the live map read it
    assert roll == {"A": b.Parcel(1968, "RM-5", rows=2), "B": b.Parcel(None, None), "C": b.Parcel(None, "C-5")}


def test_a_stray_old_row_does_not_date_a_strata_tower() -> None:
    # the Mirabel, 2021: 149 unit rows and one row still carrying the 1951 building of the old lot
    rows = [{"land_coordinate": "A", "year_built": "2021", "big_improvement_year": "2021"}] * 149
    rows.append({"land_coordinate": "A", "year_built": "1951", "big_improvement_year": "1951"})
    assert b.parcels_from_roll(rows)["A"].year_built == 2021


def test_improvement_year_goes_out_when_most_rows_agree() -> None:
    # Tudor Manor: a 1928 house front with a tower added behind it in 1989, every unit row saying so
    tudor: list[dict[str, str | None]] = [
        {"land_coordinate": "T", "year_built": "1928", "big_improvement_year": "1989"}
    ] * 3
    split: list[dict[str, str | None]] = [
        {"land_coordinate": "S", "year_built": "1960", "big_improvement_year": "1995"},
        {"land_coordinate": "S", "year_built": "1960", "big_improvement_year": "1960"},
        {"land_coordinate": "S", "year_built": "1960", "big_improvement_year": None},
    ]
    roll = b.parcels_from_roll(tudor + split)
    assert (roll["T"].year_built, roll["T"].year_improved) == (1928, 1989)
    assert roll["S"].year_improved is None


def test_stacked_parcels_take_the_dated_one_with_most_rows() -> None:
    whole = sq(0, 0, 10, 10)
    parcels = fc((whole, {"tax_coord": "1"}), (whole, {"tax_coord": "2"}), (whole, {"tax_coord": "3"}))
    rows = [{"land_coordinate": "2", "year_built": "2019"}, *[{"land_coordinate": "3", "year_built": "2018"}] * 2]
    idx = b.ParcelIndex(parcels, b.parcels_from_roll(rows))
    out = b.survey_buildings(fc((sq(2, 2, 3, 3), {"object_id": 1})), idx)
    assert out[0].props["year_built"] == 2018


def test_footprint_takes_the_year_of_the_parcel_under_its_centroid() -> None:
    idx = _index([{"land_coordinate": "A", "year_built": "1910"}, {"land_coordinate": "B", "year_built": "1965"}])
    # the second footprint straddles both parcels but its centroid is on B
    footprints = fc(
        (sq(2, 2, 3, 3), {"object_id": 1}),
        (sq(8, 2, 6, 3), {"object_id": 2}),
        (sq(22, 2, 3, 3), {"object_id": 3}),
        (sq(40, 2, 3, 3), {"object_id": 4}),
    )
    got = {f.id: (f.props["year_built"], f.props["year_source"]) for f in b.survey_buildings(footprints, idx)}
    assert got == {
        "van15-1": (1910, "tax_roll"),
        "van15-2": (1965, "tax_roll"),
        "van15-3": (None, None),
        "van15-4": (None, None),
    }


def test_osm_height_rules() -> None:
    assert b.osm_height({"height": "45 m", "building:levels": "14"}) == (45.0, 14)
    assert b.osm_height({"height": "93", "building:levels": "4"}) == (
        round(4 * 3.8, 2),
        4,
    )  # 23 m a storey: not trusted
    assert b.osm_height({"building": "apartments", "building:levels": "10"}) == (34.0, 10)
    assert b.osm_height({"building": "office", "building:levels": "2"}) == (8.4, 2)
    assert b.osm_height({"height": "100 ft"}) == (30.48, None)
    assert b.osm_height({"building": "yes"}) == (None, None)


def test_osm_outlines_skip_what_is_not_a_standing_building() -> None:
    raw = {
        "elements": [
            way(1, sq(0, 0, 3, 3), building="apartments"),
            way(2, sq(5, 0, 3, 3), building="roof"),
            way(3, sq(10, 0, 3, 3), building="yes", location="underground"),
            way(4, sq(15, 0, 3, 3), building="yes", layer="-1"),
            way(5, sq(20, 0, 0.3, 0.3), building="shed"),  # about 4 m²
            way(6, sq(25, 0, 3, 3), highway="pedestrian"),
        ]
    }
    assert [el["id"] for el, _ in b.osm_outlines(raw, M2)] == [1]


def test_new_building_year_order() -> None:
    assert b.new_building_year({"start_date": "c. 2019-05"}, b.Parcel(1960, None), True, 2016) == (2019, "osm")
    assert b.new_building_year({}, b.Parcel(2018, None), True, 2016) == (2018, "tax_roll")
    assert b.new_building_year({}, b.Parcel(1960, None), True, 2016) == (2016, "convention")
    assert b.new_building_year({}, b.Parcel(1960, None), False, 2016) == (1960, "tax_roll")
    assert b.new_building_year({}, None, False, 2016) == (2016, "convention")


def _survey(idx: b.ParcelIndex) -> list[Feature]:
    return b.survey_buildings(fc((sq(1, 1, 4, 4), {"object_id": 1})), idx)


def test_osm_building_on_survey_footprint_is_the_same_building_and_lends_its_height() -> None:
    idx = _index([{"land_coordinate": "A", "year_built": "1960"}])
    osm = [(way(9, sq(1.2, 1.2, 4, 4), building="apartments", height="30"), sq(1.2, 1.2, 4, 4))]
    merged = b.merge_osm(_survey(idx), osm, idx, 2016)
    assert [f.id for f in merged] == ["van15-1"]
    assert merged[0].props["height_m"] == 30.0
    assert merged[0].props["year_built"] == 1960


def test_partial_overlap_is_neither_new_nor_the_same() -> None:
    idx = _index([])
    outline = sq(3, 1, 4, 4)  # half on the footprint
    merged = b.merge_osm(_survey(idx), [(way(9, outline, building="yes", height="9"), outline)], idx, 2016)
    assert [f.id for f in merged] == ["van15-1"]
    assert merged[0].props["height_m"] is None


@pytest.mark.parametrize(("roll_year", "expected"), [("2021", (2021, "tax_roll")), ("1955", (2016, "convention"))])
def test_building_missing_from_the_survey_is_added(roll_year: str, expected: tuple[int, str]) -> None:
    idx = _index([{"land_coordinate": "A", "year_built": roll_year}])
    outline = sq(6, 6, 3, 3)  # on parcel A, which the survey footprint also stands on
    merged = b.merge_osm(
        _survey(idx), [(way(9, outline, building="residential", **{"building:levels": "3"}), outline)], idx, 2016
    )
    new = [f for f in merged if f.id == "osm-w9"]
    assert len(new) == 1
    p = new[0].props
    assert (p["year_built"], p["year_source"]) == expected
    assert (p["height_m"], p["levels"], p["use"], p["source"]) == (10.2, 3, "residential", "osm")
