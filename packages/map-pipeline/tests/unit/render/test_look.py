from dataclasses import replace

from qipu_map.render.look import GLASS_BY_ERA, building_look, glass_for

from .scenes import building


def test_glass_follows_the_decade() -> None:
    assert glass_for(1972, "x") in GLASS_BY_ERA[0][1]
    assert glass_for(1980, "x") in GLASS_BY_ERA[1][1]
    assert glass_for(2009, "x") in GLASS_BY_ERA[1][1]
    assert glass_for(2010, "x") in GLASS_BY_ERA[2][1]
    assert glass_for(None, "x") in GLASS_BY_ERA[1][1]


def test_a_building_keeps_its_colours_across_years_and_runs() -> None:
    b = building("bld-42", (0, 0, 10, 10), 20)
    assert building_look(b) == building_look(replace(b, height_m=25))
    looks = {building_look(building(f"b{i}", (0, 0, 10, 10), 20)).wall for i in range(40)}
    assert len(looks) > 1
