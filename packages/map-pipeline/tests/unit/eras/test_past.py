import pytest

from qipu_map.eras.past import derive_past_scene, prepare_today
from qipu_map.eras.rules import AreaOverride, Basis, DatedFeature
from qipu_map.geo.projection import LocalProjection
from qipu_map.model import BuildingType, StreetKind, YearSource

from .factory import building, old_street, park, rules, scene, street, tree

# An origin at (0, 0) degrees makes a degree polygon easy to place: 0.001 degree is about 111 m.
PROJ = LocalProjection(lon0=0.0, lat0=0.0)


def _box(m: float) -> tuple[tuple[float, float], ...]:
    d = m / 111_320.0
    return ((-d, -d), (d, -d), (d, d), (-d, d))


def test_built_and_demolished_boundaries() -> None:
    today = scene((building("new", 0, 0, 1972), building("gone", 50, 0, 1900, demolished=1972)))
    r = rules()
    before = derive_past_scene(prepare_today(today, r), 1971, r, PROJ)
    on = derive_past_scene(prepare_today(today, r), 1972, r, PROJ)
    assert [b.id for b in before.buildings] == ["gone"]
    assert [b.id for b in on.buildings] == ["new"]
    assert on.year == 1972
    assert on.notes["eras"]["derived_from"] == 2026


def test_undated_buildings_get_their_neighbours_year() -> None:
    today = scene((building("u", 0, 0, None), building("n", 20, 0, 1960)))
    r = rules()
    past = derive_past_scene(prepare_today(today, r), 1950, r, PROJ)
    assert past.buildings == ()


def test_the_past_scene_holds_stand_ins() -> None:
    tower = building("tower", 0, 20, 1975, height=60.0, kind=BuildingType.POINT_TOWER)
    r = rules()
    past = derive_past_scene(prepare_today(scene((*old_street(1905), tower)), r), 1950, r, PROJ)
    assert "tower~standin" in {b.id for b in past.buildings}
    assert past.notes["eras"]["counts"]["stand-ins (convention)"] == 1


def test_sourced_records_are_never_contradicted() -> None:
    blds = (*old_street(1905), building("tower", 0, 20, 1975), building("u", 300, 300, None))
    r = rules(areas=(AreaOverride("bay", _box(500), -10_000, 1960, Basis.CONVENTION, "s", water=True),))
    today = prepare_today(scene(blds), r)
    for year in (1900, 1905, 1930, 1950, 1980):
        past = derive_past_scene(today, year, r, PROJ)
        ids = {b.id for b in past.buildings}
        for b in today.buildings:
            if b.year_source is not YearSource.CONVENTION:
                assert (b.id in ids) == b.stands_in(year), (year, b.id)
        fps = {b.footprint for b in past.buildings if b.year_source is not YearSource.CONVENTION}
        assert not any(s.footprint in fps for s in past.buildings if s.year_source is YearSource.CONVENTION)


def test_water_area_drops_conventions_and_adds_water() -> None:
    r = rules(areas=(AreaOverride("bay", _box(100), -10_000, 1916, Basis.SOURCED, "fill 1916", water=True),))
    today = scene(
        (building("u", 0, 0, None, source=YearSource.CONVENTION), building("n", 300, 0, 1900)),
        streets=(street("s", 0),),
        trees=(tree("t", 0, 0),),
        parks=(park("p", 0, 0),),
    )
    past = derive_past_scene(prepare_today(today, r), 1910, r, PROJ)
    assert [b.id for b in past.buildings] == ["n"]
    assert past.streets == ()
    assert past.trees == ()
    assert past.parks == ()
    assert len(past.water) == 1
    later = derive_past_scene(prepare_today(today, r), 1920, r, PROJ)
    assert later.water == ()
    assert later.parks
    assert later.trees


def test_streets_follow_their_dates_and_undated_rail_stays_today() -> None:
    r = rules(dated=(DatedFeature("bridge", "streets", Basis.SOURCED, "w", names=("Bridge",), opened=1932),))
    today = scene(
        streets=(
            street("road", 0),
            street("bridge", 10, name="Bridge"),
            street("rail", 20, kind=StreetKind.RAIL),
            street("old", 30, year_closed=1960),
        )
    )

    def ids(y: int) -> list[str]:
        return [s.id for s in derive_past_scene(prepare_today(today, r), y, r, PROJ).streets]

    assert ids(1930) == ["road", "old"]
    assert ids(1950) == ["road", "bridge", "old"]
    assert ids(1970) == ["road", "bridge"]


def test_trees_follow_planting_years_and_area_rules() -> None:
    r = rules(
        areas=(AreaOverride("yard", _box(30), 1900, 1985, Basis.CONVENTION, "s", drop_trees=True, drop_parks=True),)
    )
    today = scene(
        trees=(tree("in", 0, 0), tree("young", 100, 0, 1990), tree("old", 100, 50, 1920)), parks=(park("p", 0, 0),)
    )
    past = derive_past_scene(prepare_today(today, r), 1950, r, PROJ)
    assert [t.id for t in past.trees] == ["old"]
    assert past.parks == ()


def test_street_frontage_keeps_streets_near_standing_buildings() -> None:
    r = rules(areas=(AreaOverride("yards", _box(200), 1900, 1985, Basis.CONVENTION, "s", street_frontage_m=20.0),))
    today = scene((building("b", 0, 0, 1900),), streets=(street("near", 10), street("far", 80)))
    past = derive_past_scene(prepare_today(today, r), 1950, r, PROJ)
    assert [s.id for s in past.streets] == ["near"]


def test_today_or_later_is_refused() -> None:
    r = rules()
    with pytest.raises(ValueError, match="before today"):
        derive_past_scene(prepare_today(scene(), r), 2026, r, PROJ)
