"""The look of the render: colours by surface, building type and era, and the light.

The look is "clear midday", chosen by side-by-side tests against real aerial photos: a high sun from the south-west, a
white city, dark glass, deep blue water, shadows cool but never violet. Both backends read the same table, so the
preview and the Blender render agree on what colour a thing is, if not on how it is lit.

Colours are sRGB triples in 0..1. A building's colours are picked from its type's list by a hash of its id, so the same
building keeps its colour from run to run and from year to year.
"""

from __future__ import annotations

from dataclasses import dataclass

from qipu_map.classes import SurfaceClass
from qipu_map.hashing import stable_seed
from qipu_map.model import Building, BuildingType

Colour = tuple[float, float, float]  # sRGB, 0..1


@dataclass(frozen=True)
class Light:
    """The sun and sky of the Blender render."""

    sun_azimuth_deg: float = 215.0
    sun_elevation_deg: float = 50.0
    sun_energy: float = 7.0
    sun_rgb: Colour = (1.0, 0.95, 0.88)
    sun_angle_deg: float = 0.8
    sky_strength: float = 0.38
    sky_in_reflections: float = 0.8
    exposure: float = -0.1
    agx_look: str = "AgX - Punchy"


# Ground surfaces in the beauty pass. Water is deep blue and asphalt dark, so the painter keeps them apart.
GROUND: dict[SurfaceClass, Colour] = {
    SurfaceClass.NONE: (0.0, 0.0, 0.0),
    SurfaceClass.GROUND: (0.62, 0.60, 0.55),
    SurfaceClass.ROAD: (0.30, 0.30, 0.31),
    SurfaceClass.SIDEWALK: (0.72, 0.71, 0.68),
    SurfaceClass.WATER: (0.07, 0.20, 0.33),
    SurfaceClass.GRASS: (0.36, 0.50, 0.26),
    SurfaceClass.TREE: (0.20, 0.33, 0.16),
    SurfaceClass.ROOF: (0.55, 0.53, 0.50),
    SurfaceClass.WALL: (0.88, 0.86, 0.82),
    SurfaceClass.RAIL: (0.40, 0.36, 0.33),
    SurfaceClass.SAND: (0.86, 0.80, 0.66),
}

_WHITE = [(0.93, 0.91, 0.86), (0.90, 0.89, 0.85), (0.86, 0.84, 0.80), (0.94, 0.92, 0.87)]
_SIDING = [(0.82, 0.80, 0.72), (0.70, 0.74, 0.72), (0.86, 0.82, 0.70), (0.62, 0.66, 0.70), (0.90, 0.88, 0.82)]
_STUCCO = [(0.90, 0.88, 0.82), (0.86, 0.82, 0.74), (0.82, 0.80, 0.76), (0.92, 0.90, 0.86)]
_BRICK = [(0.62, 0.36, 0.28), (0.70, 0.44, 0.34), (0.56, 0.34, 0.28)]
_CONCRETE = [(0.80, 0.79, 0.76), (0.74, 0.74, 0.72), (0.86, 0.85, 0.82)]
_DARK = [(0.30, 0.31, 0.32), (0.38, 0.38, 0.37), (0.24, 0.26, 0.28)]
_WORKS = [(0.90, 0.89, 0.85), (0.74, 0.74, 0.72), (0.64, 0.62, 0.58), (0.68, 0.74, 0.80)]

WALLS: dict[BuildingType, list[Colour]] = {
    BuildingType.CHARACTER_HOUSE: _SIDING,
    BuildingType.VANCOUVER_SPECIAL: _STUCCO,
    BuildingType.MODERN_HOUSE: _DARK + _WHITE,
    BuildingType.LANEWAY_HOUSE: _DARK,
    BuildingType.ROW_HOUSE: _SIDING,
    BuildingType.WALK_UP: _STUCCO,
    BuildingType.MID_RISE: _CONCRETE + _WHITE,
    BuildingType.POINT_TOWER: _WHITE,
    BuildingType.PODIUM_TOWER: _WHITE + _CONCRETE,
    BuildingType.COMMERCIAL: _BRICK + _CONCRETE,
    BuildingType.INDUSTRIAL: _WORKS,
    BuildingType.CIVIC: _BRICK + _CONCRETE,
    BuildingType.SHED: _WORKS,
}

_PITCHED = [(0.32, 0.30, 0.29), (0.40, 0.33, 0.28), (0.26, 0.27, 0.29), (0.44, 0.42, 0.40)]
_FLAT = [(0.62, 0.61, 0.58), (0.70, 0.69, 0.66), (0.55, 0.54, 0.52)]
_HOUSES = {
    BuildingType.CHARACTER_HOUSE,
    BuildingType.VANCOUVER_SPECIAL,
    BuildingType.MODERN_HOUSE,
    BuildingType.LANEWAY_HOUSE,
    BuildingType.ROW_HOUSE,
    BuildingType.SHED,
}

# Glass by the decade a building went up: bronze and brown before 1980, green-blue and grey 1980 to 2009, light
# blue-grey low-e glass from 2010. One glass for all towers would date every tower alike.
GLASS_BY_ERA: tuple[tuple[int, list[Colour]], ...] = (
    (1980, [(0.40, 0.33, 0.25), (0.34, 0.29, 0.24), (0.30, 0.28, 0.25), (0.22, 0.24, 0.26)]),
    (2010, [(0.30, 0.36, 0.38), (0.34, 0.42, 0.44), (0.26, 0.36, 0.50), (0.30, 0.32, 0.35)]),
    (10_000, [(0.50, 0.58, 0.64), (0.56, 0.62, 0.67), (0.46, 0.54, 0.60), (0.62, 0.66, 0.69)]),
)
_UNDATED_GLASS_YEAR = 1990


def _pick(choices: list[Colour], key: str, salt: str) -> Colour:
    return choices[stable_seed(f"{salt}:{key}") % len(choices)]


def glass_for(year: int | None, key: str) -> Colour:
    y = _UNDATED_GLASS_YEAR if year is None else year
    choices = next(g for limit, g in GLASS_BY_ERA if y < limit)
    return _pick(choices, key, "glass")


@dataclass(frozen=True)
class BuildingLook:
    wall: Colour
    roof: Colour
    glass: Colour


def building_look(b: Building) -> BuildingLook:
    roofs = _PITCHED if b.kind in _HOUSES else _FLAT
    return BuildingLook(
        wall=_pick(WALLS[b.kind], b.id, "wall"),
        roof=_pick(roofs, b.id, "roof"),
        glass=glass_for(b.year_built, b.id),
    )
