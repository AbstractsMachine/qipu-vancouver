import numpy as np
import pytest

from qipu_map.classes import SurfaceClass as C
from qipu_map.geo.camera import Canvas
from qipu_map.model import Raster, Scene
from qipu_map.render.frames import Frame
from qipu_map.render.look import Light
from qipu_map.render.passes import decode_ids
from qipu_map.render.preview import Passes, PreviewScene, ground_points, shade

from .scenes import CAMERA, box_mesh, building, flat, slope, small_scene


def draw(scene: Scene, terrain: Raster | None = None) -> tuple[Canvas, Passes]:
    t = terrain if terrain is not None else flat()
    canvas = Canvas.around(CAMERA, scene.box, 60.0)
    frame = Frame("f", 0, 0, canvas.width, canvas.height)
    return canvas, PreviewScene.build(scene, canvas, t, box_mesh, Light()).render(frame)


def pixel(canvas: Canvas, x: float, y: float, z: float) -> tuple[int, int]:
    px, py = canvas.to_px(x, y, z)
    return int(py), int(px)


def test_a_box_lands_where_the_canvas_says() -> None:
    canvas, p = draw(small_scene())
    ids = decode_ids(p.ids)
    roof = pixel(canvas, 30.0, 25.0, 12.0)
    assert p.classes[roof] == C.ROOF
    assert ids[roof] == 1
    wall = pixel(canvas, 30.0, 20.0, 6.0)
    assert p.classes[wall] == C.WALL
    assert ids[wall] == 1
    # the roof's corners, a pixel inside and a pixel outside
    r, c = canvas.to_px(40.0, 30.0, 12.0)
    assert ids[int(c) + 1, int(r) - 1] == 1
    assert ids[int(c) - 1, int(r) + 1] == 0


def test_a_box_hides_the_ground_behind_it() -> None:
    canvas, p = draw(small_scene())
    hidden = pixel(canvas, 30.0, 35.0, 0.0)
    assert decode_ids(p.ids)[hidden] == 1


def test_the_nearer_building_wins_whatever_the_scene_order() -> None:
    near = building("near", (20, 0, 40, 10), 40)
    far = building("far", (20, 15, 40, 25), 5)
    canvas, p = draw(small_scene((far, near)))
    behind = pixel(canvas, 30.0, 20.0, 5.0)
    assert decode_ids(p.ids)[behind] == 2


def test_ground_classes_show_through_the_camera() -> None:
    canvas, p = draw(small_scene())
    assert p.classes[pixel(canvas, 5.0, 10.0, 0.0)] == C.ROAD
    assert p.classes[pixel(canvas, 10.0, 90.0, 0.0)] == C.WATER
    assert p.classes[pixel(canvas, 85.0, 85.0, 0.0)] == C.GRASS
    assert decode_ids(p.ids)[pixel(canvas, 5.0, 10.0, 0.0)] == 0


def test_trees_are_discs_at_their_crowns() -> None:
    canvas, p = draw(small_scene())
    assert p.classes[pixel(canvas, 80.0, 20.0, 7.0)] == C.TREE


def test_buildings_not_yet_built_are_left_out() -> None:
    later = building("later", (20, 20, 40, 30), 12, year=2030)
    canvas, p = draw(small_scene((later,)))
    assert p.classes[pixel(canvas, 30.0, 25.0, 12.0)] != C.ROOF


def test_ground_points_walk_onto_hilly_terrain() -> None:
    terrain = slope()
    canvas = Canvas.around(CAMERA, (0.0, 0.0, 100.0, 100.0), 60.0)
    frame = Frame("f", 10, 20, 40, 30)
    x, y = ground_points(canvas, frame, terrain)
    z = terrain.sample(x.ravel(), y.ravel())
    px = canvas.to_px_array(np.stack([x.ravel(), y.ravel(), z], axis=1))
    u, v = np.meshgrid(np.arange(40) + 10.5, np.arange(30) + 20.5)
    assert px[:, 0] == pytest.approx(u.ravel(), abs=0.01)
    assert px[:, 1] == pytest.approx(v.ravel(), abs=0.01)


def test_sunlit_walls_are_brighter_than_shaded_ones() -> None:
    light = Light()
    assert shade((0.5, 0.5, 0.5), 0.9, light)[0] > shade((0.5, 0.5, 0.5), -0.3, light)[0]
    assert shade((0.5, 0.5, 0.5), np.sin(np.radians(50.0)), light) == (128, 128, 128)
