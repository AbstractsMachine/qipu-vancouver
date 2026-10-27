"""The map's fixed oblique view, and the pixel canvas it defines.

The camera is orthographic. It looks toward an azimuth (0 = north) and down at an elevation angle below the horizon, so
the fronts of buildings facing the viewer are visible and a building's height moves its roof up the image. For a world
point (x, y, z) in metres:

    screen x = x cos(a) - y sin(a)
    screen y = (x sin(a) + y cos(a)) sin(e) + z cos(e)

and the canvas pixel at the deepest zoom is ((sx - left) / m, (top - sy) / m), with m metres per pixel. Every stage that
puts something on the canvas (the render's frames, the paint grid, the tile pyramid, the era date maps, the viewer's
pins) uses these two lines, so they agree to the pixel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from qipu_map.config import Camera


@dataclass(frozen=True)
class ObliqueCamera:
    azimuth_deg: float
    elevation_deg: float
    metres_per_px: float

    @classmethod
    def from_config(cls, c: Camera) -> ObliqueCamera:
        return cls(c.azimuth_deg, c.elevation_deg, c.metres_per_px)

    @property
    def forward(self) -> tuple[float, float, float]:
        """The unit view direction in world axes (x east, y north, z up)."""
        a, e = math.radians(self.azimuth_deg), math.radians(self.elevation_deg)
        return (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), -math.sin(e))

    @property
    def up(self) -> tuple[float, float, float]:
        """The unit vector that points up the image."""
        a, e = math.radians(self.azimuth_deg), math.radians(self.elevation_deg)
        return (math.sin(a) * math.sin(e), math.cos(a) * math.sin(e), math.cos(e))

    @property
    def right(self) -> tuple[float, float, float]:
        a = math.radians(self.azimuth_deg)
        return (math.cos(a), -math.sin(a), 0.0)

    def to_screen(self, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        """World metres to screen metres (x right, y up)."""
        rx, ry, _ = self.right
        ux, uy, uz = self.up
        return (x * rx + y * ry, x * ux + y * uy + z * uz)

    def to_screen_array(self, xyz: NDArray[np.float64]) -> NDArray[np.float64]:
        """An (n, 3) array of world points to an (n, 2) array of screen metres."""
        m = np.array([self.right, self.up], dtype=np.float64).T
        out: NDArray[np.float64] = xyz @ m
        return out

    def ground_from_screen(self, sx: float, sy: float, z: float = 0.0) -> tuple[float, float]:
        """The world (x, y) at height z that the screen point (sx, sy) shows."""
        x, y = self.ground_from_screen_array(np.asarray(sx), np.asarray(sy), np.asarray(z))
        return float(x), float(y)

    def ground_from_screen_array(
        self, sx: NDArray[np.float64], sy: NDArray[np.float64], z: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """`ground_from_screen` over arrays of the same shape."""
        a, e = math.radians(self.azimuth_deg), math.radians(self.elevation_deg)
        along = (sy - z * math.cos(e)) / math.sin(e)
        return sx * math.cos(a) + along * math.sin(a), -sx * math.sin(a) + along * math.cos(a)


@dataclass(frozen=True)
class Canvas:
    """The pixel plane of the deepest zoom: screen metres to pixels, and its size.

    `left` and `top` are the screen coordinates (metres) of the canvas's top-left corner. `around` puts them on whole
    pixels of the screen plane, so every canvas of a city shares one pixel grid: the paint grid, the dissolve noise and
    two neighbouring areas line up exactly.
    """

    camera: ObliqueCamera
    left: float
    top: float
    width: int
    height: int

    @classmethod
    def around(
        cls, camera: ObliqueCamera, box: tuple[float, float, float, float], max_height_m: float, pad_px: int = 0
    ) -> Canvas:
        """The smallest canvas that shows a world box (x0, y0, x1, y1) with everything up to `max_height_m` tall in
        it."""
        corners = [(x, y, z) for x in (box[0], box[2]) for y in (box[1], box[3]) for z in (0.0, max_height_m)]
        pts = [camera.to_screen(*c) for c in corners]
        sxs, sys_ = [p[0] for p in pts], [p[1] for p in pts]
        m = camera.metres_per_px
        left = (math.floor(min(sxs) / m) - pad_px) * m
        top = (math.ceil(max(sys_) / m) + pad_px) * m
        width = math.ceil((max(sxs) - left) / m) + pad_px
        height = math.ceil((top - min(sys_)) / m) + pad_px
        return cls(camera, left, top, width, height)

    @property
    def world_px(self) -> tuple[int, int]:
        """The canvas's top-left pixel on the screen plane's pixel grid (x right, y down from screen y = 0)."""
        m = self.camera.metres_per_px
        x, y = self.left / m, -self.top / m
        if abs(x - round(x)) > 1e-6 or abs(y - round(y)) > 1e-6:
            raise ValueError(f"the canvas corner ({self.left}, {self.top}) is not on a whole pixel of {m} m")
        return round(x), round(y)

    def to_px(self, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        sx, sy = self.camera.to_screen(x, y, z)
        m = self.camera.metres_per_px
        return ((sx - self.left) / m, (self.top - sy) / m)

    def to_px_array(self, xyz: NDArray[np.float64]) -> NDArray[np.float64]:
        s = self.camera.to_screen_array(xyz)
        m = self.camera.metres_per_px
        return np.stack([(s[:, 0] - self.left) / m, (self.top - s[:, 1]) / m], axis=1)

    def affine(self) -> list[list[float]]:
        """The 2x4 matrix that maps (x, y, z, 1) in world metres to canvas pixels. The viewer uses it to place pins."""
        m = self.camera.metres_per_px
        rx, ry, rz = self.camera.right
        ux, uy, uz = self.camera.up
        return [
            [rx / m, ry / m, rz / m, -self.left / m],
            [-ux / m, -uy / m, -uz / m, self.top / m],
        ]
