"""Surface classes of the render's class pass.

The renderer writes, next to each beauty frame, an 8-bit image where every pixel holds the id of the surface it shows.
The painter reads it to choose prompts and to keep water and other protected surfaces from the render; the era stage
reads it to find what changed between two years. The ids are part of the file format: never renumber them.
"""

from __future__ import annotations

from enum import IntEnum


class SurfaceClass(IntEnum):
    NONE = 0
    GROUND = 1
    ROAD = 2
    SIDEWALK = 3
    WATER = 4
    GRASS = 5
    TREE = 6
    ROOF = 7
    WALL = 8
    RAIL = 9
    SAND = 10


# Flat colours of the class pass, chosen far apart so a renderer's anti-aliasing cannot turn one class into another.
CLASS_COLOURS: dict[SurfaceClass, tuple[int, int, int]] = {
    SurfaceClass.NONE: (0, 0, 0),
    SurfaceClass.GROUND: (128, 96, 64),
    SurfaceClass.ROAD: (64, 64, 64),
    SurfaceClass.SIDEWALK: (192, 192, 192),
    SurfaceClass.WATER: (0, 64, 255),
    SurfaceClass.GRASS: (64, 200, 64),
    SurfaceClass.TREE: (0, 112, 0),
    SurfaceClass.ROOF: (255, 0, 0),
    SurfaceClass.WALL: (255, 160, 0),
    SurfaceClass.RAIL: (128, 0, 128),
    SurfaceClass.SAND: (240, 220, 140),
}
