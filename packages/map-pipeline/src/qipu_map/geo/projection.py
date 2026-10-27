"""Degrees to local metres and back.

The map uses a plain equirectangular projection around a city origin. Over a city
(about 15 km) its distortion is well under a metre, and it keeps every stage free of a projection library.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, overload

import numpy as np
from numpy.typing import NDArray

from qipu_map.config import Projection
from qipu_map.geo.boxes import GeoBox, WorldBox

Point = tuple[float, float]
_F = NDArray[np.float64]


@dataclass(frozen=True)
class LocalProjection:
    """Equirectangular projection around a city origin: degrees to local metres (x east, y north) and back."""

    lon0: float
    lat0: float
    metres_per_degree: float = 111_320.0

    @classmethod
    def from_config(cls, p: Projection) -> LocalProjection:
        return cls(p.lon0, p.lat0, p.metres_per_degree)

    @property
    def kx(self) -> float:
        return self.metres_per_degree * math.cos(math.radians(self.lat0))

    @property
    def ky(self) -> float:
        return self.metres_per_degree

    @overload
    def to_world(self, lon: float, lat: float) -> Point: ...
    @overload
    def to_world(self, lon: _F, lat: _F) -> tuple[_F, _F]: ...
    def to_world(self, lon: float | _F, lat: float | _F) -> tuple[Any, Any]:
        """Degrees to metres, for one point or for arrays of them."""
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    @overload
    def to_lonlat(self, x: float, y: float) -> Point: ...
    @overload
    def to_lonlat(self, x: _F, y: _F) -> tuple[_F, _F]: ...
    def to_lonlat(self, x: float | _F, y: float | _F) -> tuple[Any, Any]:
        """Metres to degrees, for one point or for arrays of them."""
        return (self.lon0 + x / self.kx, self.lat0 + y / self.ky)

    def box_to_world(self, bbox: GeoBox) -> WorldBox:
        x0, y0 = self.to_world(bbox.west, bbox.south)
        x1, y1 = self.to_world(bbox.east, bbox.north)
        return WorldBox(x0, y0, x1, y1)
