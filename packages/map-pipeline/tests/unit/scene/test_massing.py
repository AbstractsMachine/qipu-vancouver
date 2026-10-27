from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pytest

from qipu_map.classes import SurfaceClass
from qipu_map.model import Building, BuildingType, Ring, RoofForm, YearSource
from qipu_map.scene.massing import FOOT_M, MAX_RISE_SHARE, PITCH_DEG, Mesh, building_mesh

HOUSE: Ring = ((0.0, 0.0), (8.0, 0.0), (8.0, 14.0), (0.0, 14.0))
L_SHAPE: Ring = ((0.0, 0.0), (12.0, 0.0), (12.0, 5.0), (5.0, 5.0), (5.0, 12.0), (0.0, 12.0))
ROTATED: Ring = tuple(
    (x * math.cos(0.5) - y * math.sin(0.5) + 100, x * math.sin(0.5) + y * math.cos(0.5) + 50) for x, y in HOUSE
)


def house(
    footprint: Ring = HOUSE,
    roof: RoofForm = RoofForm.GABLE,
    height: float = 9.0,
    kind: BuildingType = BuildingType.CHARACTER_HOUSE,
) -> Building:
    return Building("h", footprint, 10.0, height, roof, kind, 1912, YearSource.TAX_ROLL)


def directed_edges(m: Mesh) -> Counter[tuple[int, int]]:
    return Counter((f[i], f[(i + 1) % len(f)]) for f in m.faces for i in range(len(f)))


def normal(m: Mesh, face: tuple[int, ...]) -> np.ndarray:
    """Newell's normal of a face."""
    p = m.vertices[list(face)]
    q = np.roll(p, -1, axis=0)
    return np.array(
        [
            ((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])).sum(),
            ((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])).sum(),
            ((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1])).sum(),
        ]
    )


def ridge(m: Mesh, top: float = 19.0) -> tuple[tuple[float, float], tuple[float, float]]:
    """The x range and y range of the vertices at the top of the roof."""
    p = m.vertices[np.isclose(m.vertices[:, 2], top)]
    return (float(np.min(p[:, 0])), float(np.max(p[:, 0]))), (float(np.min(p[:, 1])), float(np.max(p[:, 1])))


def signed_volume(m: Mesh) -> float:
    v = 0.0
    for f in m.faces:
        a = m.vertices[f[0]]
        for i in range(1, len(f) - 1):
            v += float(np.dot(a, np.cross(m.vertices[f[i]], m.vertices[f[i + 1]]))) / 6
    return v


@pytest.mark.parametrize("roof", list(RoofForm))
@pytest.mark.parametrize("footprint", [HOUSE, L_SHAPE, ROTATED, tuple(reversed(HOUSE))])
def test_mesh_is_closed_and_faces_point_outward(roof: RoofForm, footprint: Ring) -> None:
    m = building_mesh(house(footprint, roof))
    edges = directed_edges(m)
    assert all(n == 1 and edges[(b, a)] == 1 for (a, b), n in edges.items())
    assert signed_volume(m) > 0


def test_flat_box_has_the_expected_faces_and_volume() -> None:
    m = building_mesh(house(roof=RoofForm.FLAT, height=12.0))
    assert len(m.vertices) == 8
    assert m.face_class.count(SurfaceClass.ROOF) == 2
    assert m.face_class.count(SurfaceClass.WALL) == 4 + 2
    assert signed_volume(m) == pytest.approx(8 * 14 * (12 + FOOT_M))
    roof_z = {
        float(m.vertices[i, 2]) for f, c in zip(m.faces, m.face_class, strict=True) if c is SurfaceClass.ROOF for i in f
    }
    assert roof_z == {22.0}


def test_roof_faces_look_up_and_walls_sideways() -> None:
    m = building_mesh(house(roof=RoofForm.HIP))
    for f, c in zip(m.faces, m.face_class, strict=True):
        n = normal(m, f)
        n = n / np.linalg.norm(n)
        if c is SurfaceClass.ROOF:
            assert n[2] > 0.5
        elif n[2] > -0.5:
            assert abs(n[2]) < 1e-9


def test_gable_ridge_runs_along_the_long_side_at_the_top() -> None:
    m = building_mesh(house(roof=RoofForm.GABLE))
    assert ridge(m) == ((4.0, 4.0), (0.0, 14.0))
    rise = min(4.0 * math.tan(math.radians(PITCH_DEG[BuildingType.CHARACTER_HOUSE])), MAX_RISE_SHARE * 9.0)
    eave = m.vertices[(m.vertices[:, 0] == 0.0) & (m.vertices[:, 2] > 10.0)][:, 2]
    assert np.allclose(eave, 19.0 - rise)


def test_vancouver_special_has_its_ridge_across_the_lot() -> None:
    m = building_mesh(house(roof=RoofForm.GABLE, kind=BuildingType.VANCOUVER_SPECIAL))
    assert ridge(m) == ((0.0, 8.0), (7.0, 7.0))


def test_hip_ridge_is_shorter_than_the_house() -> None:
    m = building_mesh(house(roof=RoofForm.HIP))
    assert ridge(m) == ((4.0, 4.0), (4.0, 10.0))
    assert max(len(f) for f, c in zip(m.faces, m.face_class, strict=True) if c is SurfaceClass.ROOF) == 3
    assert m.face_class.count(SurfaceClass.ROOF) <= 32


def test_big_and_tall_buildings_get_flat_roofs() -> None:
    big = ((0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0))
    assert len(building_mesh(house(big, RoofForm.GABLE)).vertices) == 8
    assert len(building_mesh(house(HOUSE, RoofForm.HIP, height=30.0)).vertices) == 8


def test_tiny_footprint_falls_back_to_flat() -> None:
    sliver = ((0.0, 0.0), (0.8, 0.0), (0.8, 5.0), (0.0, 5.0))
    assert len(building_mesh(house(sliver, RoofForm.GABLE)).vertices) == 8


def test_mesh_is_deterministic() -> None:
    a, b = building_mesh(house(L_SHAPE, RoofForm.HIP)), building_mesh(house(L_SHAPE, RoofForm.HIP))
    assert a.faces == b.faces
    assert np.array_equal(a.vertices, b.vertices)
