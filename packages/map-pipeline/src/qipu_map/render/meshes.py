"""Building meshes as the render sees them.

The scene stage turns each building into a closed mesh (`qipu_map.scene.massing.building_mesh`): vertices in world
metres, faces as vertex-index loops counter-clockwise seen from outside, and a surface class per face (ROOF or WALL).
The render only needs that shape of data, so it asks for it through a protocol and takes the mesher as a parameter;
tests pass a plain box mesher.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from qipu_map.classes import SurfaceClass
from qipu_map.model import Building


class MeshLike(Protocol):
    @property
    def vertices(self) -> NDArray[np.float64]: ...

    @property
    def faces(self) -> Sequence[Sequence[int]]: ...

    @property
    def face_class(self) -> Sequence[SurfaceClass]: ...


Mesher = Callable[[Building], MeshLike]


def default_mesher() -> Mesher:
    """The scene stage's mesher. Imported when needed, so the render's own modules load without it."""
    from qipu_map.scene.massing import building_mesh  # noqa: PLC0415

    mesher: Mesher = building_mesh
    return mesher


def face_normal(points: NDArray[np.float64]) -> NDArray[np.float64]:
    """The unit normal of a planar-ish polygon (Newell's method), pointing out of a counter-clockwise loop."""
    nxt = np.roll(points, -1, axis=0)
    n = np.array(
        [
            np.sum((points[:, 1] - nxt[:, 1]) * (points[:, 2] + nxt[:, 2])),
            np.sum((points[:, 2] - nxt[:, 2]) * (points[:, 0] + nxt[:, 0])),
            np.sum((points[:, 0] - nxt[:, 0]) * (points[:, 1] + nxt[:, 1])),
        ]
    )
    length = float(np.linalg.norm(n))
    out: NDArray[np.float64] = n / length if length > 0 else n
    return out
