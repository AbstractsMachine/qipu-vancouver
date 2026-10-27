import math

import shapely

from qipu_map.eras.lots import HOUSE_MAX_HEIGHT_M, SIDE_YARD_M, split_into_houses
from qipu_map.eras.standins import stand_ins
from qipu_map.model import Building, BuildingType, RoofForm, YearSource

from .factory import STANDINS, building, old_street


def _stand_in(ring: tuple[tuple[float, float], ...], height: float = 30.0) -> Building:
    return Building(
        id="t~standin",
        footprint=ring,
        ground_m=4.0,
        height_m=height,
        roof=RoofForm.FLAT,
        kind=BuildingType.WALK_UP,
        year_built=1905,
        year_source=YearSource.CONVENTION,
        demolished=1975,
    )


def _rect(w: float, d: float, angle_deg: float = 0.0) -> tuple[tuple[float, float], ...]:
    a = math.radians(angle_deg)
    u, v = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    return tuple((x * u[0] + y * v[0], x * u[1] + y * v[1]) for x, y in ((0, 0), (w, 0), (w, d), (0, d)))


def test_a_small_stand_in_stays_whole() -> None:
    s = _stand_in(_rect(15, 15))
    assert split_into_houses(s, 10.0, 37.0, 300.0) == (s,)


def test_a_tower_lot_becomes_a_row_of_houses() -> None:
    s = _stand_in(_rect(40, 30, angle_deg=25))
    houses = split_into_houses(s, 10.0, 37.0, 300.0)
    assert [h.id for h in houses] == [f"t~standin-s{k}" for k in range(4)]
    fp = shapely.Polygon(s.footprint)
    for h in houses:
        p = shapely.Polygon(h.footprint)
        assert p.exterior.is_ccw
        assert p.area < 150
        assert fp.contains(p.buffer(-0.01))
        assert (h.kind, h.roof, h.height_m) == (BuildingType.CHARACTER_HOUSE, RoofForm.GABLE, HOUSE_MAX_HEIGHT_M)
        assert (h.year_built, h.demolished, h.year_source, h.ground_m) == (1905, 1975, YearSource.CONVENTION, 4.0)
    polys = [shapely.Polygon(h.footprint) for h in houses]
    gaps = [polys[i].distance(polys[i + 1]) for i in range(len(polys) - 1)]
    assert all(abs(g - 2 * SIDE_YARD_M) < 1e-3 for g in gaps)  # side yards between neighbours


def test_a_deep_block_gets_rows_and_a_shaped_footprint_keeps_only_inside_lots() -> None:
    long = split_into_houses(_stand_in(_rect(20, 74)), 10.0, 37.0, 300.0)
    assert len(long) == 7  # lots run across the long side
    deep = split_into_houses(_stand_in(_rect(80, 60)), 10.0, 37.0, 300.0)
    assert len(deep) == 16  # two rows of eight back to back
    ell = ((0.0, 0.0), (50.0, 0.0), (50.0, 12.0), (10.0, 12.0), (10.0, 40.0), (0.0, 40.0))
    houses = split_into_houses(_stand_in(ell), 10.0, 37.0, 300.0)
    fp = shapely.Polygon(ell)
    assert houses
    assert all(
        shapely.intersection(shapely.Polygon(h.footprint), fp).area >= 0.7 * shapely.Polygon(h.footprint).area
        for h in houses
    )


def test_split_is_deterministic_and_low_houses_keep_their_height() -> None:
    s = _stand_in(_rect(40, 30, angle_deg=-12), height=8.0)
    a, b = split_into_houses(s, 10.0, 37.0, 300.0), split_into_houses(s, 10.0, 37.0, 300.0)
    assert a == b
    assert all(h.height_m == 8.0 for h in a)


def test_stand_ins_split_a_tower_footprint() -> None:
    tower = building("tower", 0.0, 40.0, 1975, height=60.0, side=30.0)
    out = stand_ins((*old_street(1905), tower), 1950, STANDINS)
    assert len(out) == 3
    assert all(h.id.startswith("tower~standin-s") for h in out)
