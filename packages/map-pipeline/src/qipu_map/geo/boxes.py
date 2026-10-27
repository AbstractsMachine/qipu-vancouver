"""Boxes: an area in degrees (`GeoBox`) and in local metres (`WorldBox`).

Both are named tuples, so they unpack, compare and serialise to JSON as the plain four numbers they stand for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import shapely

if TYPE_CHECKING:
    from qipu_map.geo.projection import LocalProjection


class GeoBox(NamedTuple):
    """A box in degrees, in the order Overpass and the city files use."""

    south: float
    west: float
    north: float
    east: float

    def grown(self, margin_m: float, projection: LocalProjection) -> GeoBox:
        """The box grown by `margin_m` metres on every side."""
        dlat, dlon = margin_m / projection.ky, margin_m / projection.kx
        return GeoBox(self.south - dlat, self.west - dlon, self.north + dlat, self.east + dlon)

    def wkt(self) -> str:
        s, w, n, e = self
        return f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

    def overpass(self) -> str:
        return f"({self.south},{self.west},{self.north},{self.east})"

    def shape(self) -> shapely.Polygon:
        """The box as a polygon in (lon, lat)."""
        return shapely.box(self.west, self.south, self.east, self.north)


class WorldBox(NamedTuple):
    """A box in local metres: x east, y north."""

    x0: float
    y0: float
    x1: float
    y1: float

    def grown(self, by: float) -> WorldBox:
        return WorldBox(self.x0 - by, self.y0 - by, self.x1 + by, self.y1 + by)

    def intersects(self, other: WorldBox) -> bool:
        return self.x0 <= other.x1 and other.x0 <= self.x1 and self.y0 <= other.y1 and other.y0 <= self.y1

    def shape(self) -> shapely.Polygon:
        return shapely.box(*self)
