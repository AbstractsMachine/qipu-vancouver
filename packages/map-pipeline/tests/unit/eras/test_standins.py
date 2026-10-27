from dataclasses import replace

import numpy as np

from qipu_map.eras.rules import Evidence
from qipu_map.eras.standins import STANDIN_SUFFIX, evidence_level, stand_ins
from qipu_map.model import Building, BuildingType, Raster, RoofForm, YearSource

from .factory import STANDINS, building, old_street


def _tower(year: int = 1975) -> Building:
    return building("tower", 0.0, 20.0, year, height=60.0, kind=BuildingType.POINT_TOWER)


def test_a_new_tower_on_an_old_street_gets_a_stand_in() -> None:
    blds = (*old_street(1905), _tower(1975))
    out = stand_ins(blds, 1950, STANDINS)
    assert len(out) == 1
    s = out[0]
    assert s.id == "tower" + STANDIN_SUFFIX
    assert s.footprint == blds[-1].footprint
    assert (s.year_built, s.demolished, s.year_source) == (1905, 1975, YearSource.CONVENTION)
    assert s.height_m == 9.0
    assert s.kind is BuildingType.CHARACTER_HOUSE
    assert s.roof is RoofForm.GABLE
    assert s.stands_in(1950)
    assert not s.stands_in(1975)


def test_no_stand_in_once_the_record_stands_or_on_a_young_street() -> None:
    blds = (*old_street(1905), _tower(1975))
    assert stand_ins(blds, 1980, STANDINS) == ()
    young = (*old_street(1960), _tower(1975))
    assert stand_ins(young, 1965, STANDINS) == ()


def test_too_few_old_neighbours_means_no_stand_in() -> None:
    blds = (*old_street(1905, n=4), _tower(1975))
    assert stand_ins(blds, 1950, STANDINS) == ()


def test_stand_in_year_never_after_the_year_shown() -> None:
    blds = (*old_street(1925), _tower(1975))
    out = stand_ins(blds, 1920, replace(STANDINS, old_share=0.0))
    assert out
    assert out[0].year_built == 1910


def test_early_years_cap_the_height() -> None:
    tall = tuple(replace(b, height_m=30.0) for b in old_street(1900))
    out = stand_ins((*tall, _tower(1975)), 1925, STANDINS)
    assert out[0].height_m == 14.0
    later = stand_ins((*tall, _tower(1975)), 1950, STANDINS)
    assert later[0].height_m == 30.0


def _evidence(value: float) -> tuple[Evidence, Raster]:
    ev = Evidence("photo", photo_year=1950, first_year=1930, last_year=1954)
    return ev, Raster(x0=-100.0, y0=100.0, cell=1.0, data=np.full((200, 200), value, np.float32))


def test_a_built_up_photo_is_enough_on_its_own() -> None:
    lonely = (_tower(1975),)
    assert stand_ins(lonely, 1950, STANDINS) == ()
    out = stand_ins(lonely, 1950, STANDINS, _evidence(1.0))
    assert len(out) == 1
    assert out[0].year_built == 1910
    assert stand_ins(lonely, 1950, STANDINS, _evidence(0.0)) == ()


def test_the_photo_only_speaks_for_buildings_well_after_it() -> None:
    lonely = (_tower(1953),)
    assert stand_ins(lonely, 1950, STANDINS, _evidence(1.0)) == ()


def test_evidence_level_ramps() -> None:
    assert evidence_level(None, 0, 0) == 0.0
    assert evidence_level(_evidence(0.5), 0, 0) == 0.5
    assert evidence_level(_evidence(0.9), 0, 0) == 1.0


def test_a_stand_in_never_covers_a_standing_record() -> None:
    blds = (*old_street(1905), _tower(1975), building("garage", 0.0, 20.0, 1920, side=9.0))
    assert [s.id for s in stand_ins(blds, 1950, STANDINS)] == []


def test_kind_is_the_neighbours_most_common_with_a_stable_tie_break() -> None:
    houses = old_street(1905)
    mixed = tuple(replace(b, kind=BuildingType.ROW_HOUSE) if i % 2 else b for i, b in enumerate(houses))
    out = stand_ins((*mixed, _tower(1975)), 1950, STANDINS)
    assert out[0].kind is sorted([BuildingType.ROW_HOUSE, BuildingType.CHARACTER_HOUSE])[0]
