import math

import numpy as np
import pytest

from qipu_map.geo.camera import Canvas, ObliqueCamera

CAM = ObliqueCamera(azimuth_deg=0.0, elevation_deg=30.709, metres_per_px=0.25)


def test_forward_matches_the_live_camera() -> None:
    fx, fy, fz = CAM.forward
    assert fx == pytest.approx(0.0, abs=1e-12)
    assert fy == pytest.approx(0.85977, abs=1e-4)
    assert fz == pytest.approx(-0.51068, abs=1e-4)


def test_basis_is_orthonormal() -> None:
    vecs = np.array([CAM.forward, CAM.up, CAM.right])
    assert np.allclose(vecs @ vecs.T, np.eye(3))


def test_height_moves_a_point_up_the_image() -> None:
    _, low = CAM.to_screen(10.0, 20.0, 0.0)
    _, high = CAM.to_screen(10.0, 20.0, 100.0)
    assert high - low == pytest.approx(100.0 * math.cos(math.radians(30.709)))


def test_ground_from_screen_inverts_to_screen() -> None:
    cam = ObliqueCamera(azimuth_deg=17.0, elevation_deg=40.0, metres_per_px=0.5)
    sx, sy = cam.to_screen(123.0, -45.0, 12.0)
    assert cam.ground_from_screen(sx, sy, 12.0) == pytest.approx((123.0, -45.0))


def test_canvas_holds_the_box_and_its_tallest_roof() -> None:
    box = (0.0, 0.0, 400.0, 300.0)
    canvas = Canvas.around(CAM, box, max_height_m=80.0)
    for x in (0.0, 400.0):
        for y in (0.0, 300.0):
            for z in (0.0, 80.0):
                px, py = canvas.to_px(x, y, z)
                assert -1e-6 <= px <= canvas.width + 1e-6
                assert -1e-6 <= py <= canvas.height + 1e-6
    assert canvas.width == 1600


def test_affine_agrees_with_to_px() -> None:
    cam = ObliqueCamera(azimuth_deg=-12.0, elevation_deg=30.0, metres_per_px=0.3)
    canvas = Canvas.around(cam, (-50.0, -50.0, 50.0, 50.0), 30.0, pad_px=8)
    a = np.array(canvas.affine())
    for p in [(-50.0, 10.0, 0.0), (12.5, -3.0, 25.0)]:
        assert a @ np.array([*p, 1.0]) == pytest.approx(canvas.to_px(*p))
    pts = np.array([[-50.0, 10.0, 0.0], [12.5, -3.0, 25.0]])
    assert canvas.to_px_array(pts) == pytest.approx(np.array([canvas.to_px(*p) for p in pts]))


def test_canvas_corner_is_on_a_whole_pixel() -> None:
    cam = ObliqueCamera(0.0, 30.709, 0.25)
    canvas = Canvas.around(cam, (-13.3, 7.1, 40.2, 52.9), 31.7, pad_px=3)
    x, y = canvas.world_px
    assert canvas.left == pytest.approx(x * 0.25)
    assert canvas.top == pytest.approx(-y * 0.25)
    for corner in ((-13.3, 7.1, 0.0), (40.2, 52.9, 31.7)):
        px, py = canvas.to_px(*corner)
        assert 0 <= px <= canvas.width
        assert 0 <= py <= canvas.height


def test_ground_from_screen_array_matches_the_scalar() -> None:
    cam = ObliqueCamera(20.0, 30.709, 0.25)
    sx, sy, z = np.array([1.0, -4.0]), np.array([3.0, 8.0]), np.array([0.0, 12.0])
    x, y = cam.ground_from_screen_array(sx, sy, z)
    assert (x[1], y[1]) == pytest.approx(cam.ground_from_screen(-4.0, 8.0, 12.0))
