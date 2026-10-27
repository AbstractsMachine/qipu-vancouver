import numpy as np

from qipu_map.classes import SurfaceClass as C
from qipu_map.paint.guards import THRESHOLDS, Verdict, judge

GRASS = (70, 140, 60)
BRICK = (150, 70, 50)
GREY = (165, 165, 160)  # a pale roof: its edges stand out from the grass


def scene(size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    classes = np.full((size, size), C.GRASS, np.uint8)
    render = np.empty((size, size, 3), np.uint8)
    render[:] = GRASS
    return classes, render


def test_a_vanished_building_is_caught() -> None:
    classes, render = scene()
    classes[80:150, 80:150] = C.ROOF
    render[80:150, 80:150] = BRICK
    assert judge(render, render, classes).scores["vanish"] == 0
    painted = render.copy()
    painted[80:150, 80:150] = GRASS
    v = judge(painted, render, classes)
    assert v.scores["vanish"] == 70 * 70
    assert "vanish" in v.flags


def test_a_small_building_is_not_counted() -> None:
    classes, render = scene()
    classes[10:30, 10:30] = C.ROOF
    render[10:30, 10:30] = BRICK
    painted = render.copy()
    painted[10:30, 10:30] = GRASS
    assert judge(painted, render, classes).scores["vanish"] == 0


def test_a_house_invented_on_a_meadow_is_caught() -> None:
    classes, render = scene()
    painted = render.copy()
    painted[60:180, 60:180] = GREY
    v = judge(painted, render, classes)
    assert v.scores["invent"] >= THRESHOLDS["invent"]
    assert "invent" in v.flags
    assert v.cost > judge(render, render, classes).cost


def test_thin_or_grey_on_grey_is_not_an_invention() -> None:
    classes, render = scene()
    painted = render.copy()
    painted[100:110, 10:250] = GREY  # a path or a row of logs: thin
    assert judge(painted, render, classes).scores["invent"] == 0
    grey_render = np.full_like(render, 125)  # a paved lot repainted grey: the render was not chromatic
    painted = grey_render.copy()
    painted[60:180, 60:180] = (90, 90, 90)
    assert judge(painted, grey_render, classes).scores["invent"] == 0


def test_a_white_glare_is_not_an_invention() -> None:
    # Lightness is on OpenCV's 0-255 scale, as the thresholds were tuned: white (L* 91) is past INVENT_LMAX.
    classes, render = scene()
    painted = render.copy()
    painted[60:180, 60:180] = (232, 232, 230)
    assert judge(painted, render, classes).scores["invent"] == 0


def test_inventions_next_to_buildings_are_left_alone() -> None:
    classes, render = scene()
    classes[:, :128] = C.ROOF
    painted = render.copy()
    painted[60:180, 60:180] = GREY
    assert judge(painted, render, classes).scores["invent"] < THRESHOLDS["invent"]


def test_cost_is_capped_and_flags_sorted() -> None:
    v = Verdict({"vanish": 10**9, "invent": 10**9})
    assert v.cost == 6.0
    assert v.flags == ["invent", "vanish"]
    assert Verdict({}).cost == 0.0
    assert Verdict({}).flags == []


def test_a_pier_invented_on_the_water_is_caught() -> None:
    classes, render = scene()
    classes[:] = C.WATER
    render[:] = (40, 90, 150)
    painted = render.copy()
    painted[40:200, 100:190] = GREY
    assert "invent" in judge(painted, render, classes).flags
