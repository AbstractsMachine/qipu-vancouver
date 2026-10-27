"""Today's buildings: a footprint in, a typed building with its height, ground and roof out."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np
import shapely

from qipu_map.hashing import stable_fraction
from qipu_map.model import Building, BuildingType, Raster, RoofForm, YearSource
from qipu_map.scene import heights, podium, roofs, types
from qipu_map.scene.heights import STOREY_M
from qipu_map.scene.types import Facts

# A footprint this small and taller than three times its side is a data error (a 7 m², 35 m "house" stood as a chimney).
SLIVER_MAX_M2 = 30.0
# Smaller cleaned outlines are slivers left between two traced footprints, not buildings.
MIN_OUTLINE_M2 = 4.0
TOWER_SUFFIX = "-tower"
BACK_YARD_M = 25.0  # a lot's depth: how far a house may stand from its laneway house or garage
MIN_HEIGHT_M = 2.5  # a garden shed; anything lower is a fence or a car the LiDAR read as a roof
HIP_SHARE = 0.35  # of the pitched types whose roof the LiDAR could not read, this share get a hip and the rest a gable


@dataclass(frozen=True)
class Footprint:
    """One building as ingest describes it, in local metres."""

    id: str
    outline: shapely.Polygon
    year_built: int | None
    year_source: str | None
    year_improved: int | None
    height_m: float | None
    levels: int | None
    use: str | None


@dataclass(frozen=True)
class Built:
    building: Building
    tower: Building | None  # the tower standing on this building's podium, when the LiDAR shows one
    height_source: str
    roof_source: str
    rule: str


def clean(outline: shapely.Geometry) -> shapely.Polygon | None:
    """A valid, counter-clockwise outline without holes or repeated points; the largest part of a multi-part one."""
    g = shapely.make_valid(outline)
    parts = [p for p in shapely.get_parts(g) if isinstance(p, shapely.Polygon) and not p.is_empty]
    if not parts:
        return None
    poly = max(parts, key=lambda p: p.area)
    simple = shapely.Polygon(poly.exterior).simplify(0.05)
    if not isinstance(simple, shapely.Polygon) or simple.is_empty or simple.area < MIN_OUTLINE_M2:
        return None
    oriented: shapely.Polygon = shapely.orient_polygons(simple)
    return oriented


def is_sliver(area_m2: float, height_m: float) -> bool:
    """Under 30 m² and taller than three times its side: a stray outline, not a building."""
    return area_m2 < SLIVER_MAX_M2 and height_m > 3 * math.sqrt(max(area_m2, 1.0))


def beside_bigger(footprints: list[shapely.Polygon]) -> list[bool]:
    """For each footprint, whether a bigger one stands within a lot's depth (it is then a back-yard building)."""
    tree = shapely.STRtree(footprints)
    areas = np.array([p.area for p in footprints])
    out = []
    for i, p in enumerate(footprints):
        near = tree.query(p, predicate="dwithin", distance=BACK_YARD_M)
        out.append(bool(np.any(areas[near] > 2 * areas[i])))
    return out


def build(fp: Footprint, dsm: Raster, dem: Raster, near_bigger: bool) -> Built | None:
    """The building, or None when its guards drop it."""
    poly = fp.outline
    area = poly.area
    reading = heights.read(poly, dsm, dem)
    fit = roofs.classify(poly, dsm)
    pitched = fit is not None and fit.form is not RoofForm.FLAT
    height = heights.decide(reading, fp.height_m, fp.levels, pitched=pitched)
    use = types.use_of(fp.use)
    with np.errstate(divide="ignore", invalid="ignore"):
        rect_area = shapely.minimum_rotated_rectangle(poly).area
    provisional = height.metres if height else types.USE_HEIGHT_M[use]
    facts = Facts(
        year=fp.year_built,
        height_m=provisional,
        top_m=max(provisional, reading.p90 if reading is not None and reading.cells >= heights.MIN_CELLS else 0.0),
        area_m2=area,
        fill=area / rect_area if rect_area > 0 else 1.0,
        roof=fit.form if fit else None,
        pitch_deg=fit.pitch_deg if fit else 0.0,
        use=use,
        beside_bigger=near_bigger,
    )
    kind, rule = types.classify(facts)
    metres = height.metres if height else types.DEFAULT_HEIGHT_M[kind]
    if kind is BuildingType.PODIUM_TOWER and height is None and reading is not None:
        metres = reading.p50  # a tower in a plaza: the "podium" is the open ground around it
    if is_sliver(area, metres):
        return None
    roof, roof_source = _roof(fit, kind, fp.id)
    base = _building(fp, poly, ground_m=heights.ground(poly, dem), metres=metres, roof=roof, kind=kind)
    tower = None
    if kind is BuildingType.PODIUM_TOWER:
        outline = podium.tower_outline(poly, dsm, dem, metres, facts.top_m)
        if outline is not None:
            tower = _building(
                fp,
                outline,
                ground_m=base.ground_m,
                metres=facts.top_m,
                roof=RoofForm.FLAT,
                kind=BuildingType.POINT_TOWER,
                tower=True,
            )
    return Built(base, tower, height.source.value if height else "default", roof_source, rule)


def _building(
    fp: Footprint,
    poly: shapely.Polygon,
    *,
    ground_m: float,
    metres: float,
    roof: RoofForm,
    kind: BuildingType,
    tower: bool = False,
) -> Building:
    """The scene's building for a footprint, or with `tower` for the tower split out of it (id `<id>-tower`).

    A tower counts its own storeys from its height: the record's storey count belongs to the whole outline.
    """
    ring = tuple((round(float(x), 3), round(float(y), 3)) for x, y in shapely.get_coordinates(poly.exterior)[:-1])
    return Building(
        id=f"{fp.id}{TOWER_SUFFIX if tower else ''}",
        footprint=ring,
        ground_m=round(ground_m, 2),
        height_m=round(max(metres, MIN_HEIGHT_M), 2),
        roof=roof,
        kind=kind,
        year_built=fp.year_built,
        year_source=YearSource(fp.year_source) if fp.year_source else YearSource.CONVENTION,
        storeys=(None if tower else fp.levels) or max(1, round(metres / STOREY_M)),
        year_improved=fp.year_improved,
    )


def _roof(fit: roofs.RoofFit | None, kind: BuildingType, bid: str) -> tuple[RoofForm, str]:
    """The LiDAR's roof where it read one, else the type's usual roof (pitched types: a stable draw per building)."""
    if fit is not None:
        return fit.form, "lidar"
    default = types.DEFAULT_ROOF.get(kind, RoofForm.FLAT)
    if default is RoofForm.GABLE and stable_fraction(bid) < HIP_SHARE:
        default = RoofForm.HIP
    return default, "type"


def build_all(fps: list[Footprint], dsm: Raster, dem: Raster) -> tuple[list[Building], dict[str, dict[str, int]]]:
    """Every building that survives the guards, sorted by id, and counts of how each was decided."""
    near = beside_bigger([f.outline for f in fps]) if fps else []
    out: list[Building] = []
    counts: dict[str, Counter[str]] = {"height": Counter(), "roof": Counter(), "rule": Counter(), "kind": Counter()}
    dropped = 0
    for fp, n in zip(fps, near, strict=True):
        b = build(fp, dsm, dem, n)
        if b is None:
            dropped += 1
            continue
        out.append(b.building)
        if b.tower is not None:
            out.append(b.tower)
            counts["kind"]["point_tower (on a podium)"] += 1
        counts["height"][b.height_source] += 1
        counts["roof"][b.roof_source] += 1
        counts["rule"][b.rule] += 1
        counts["kind"][b.building.kind.value] += 1
    out.sort(key=lambda b: b.id)
    notes = {k: dict(sorted(v.items())) for k, v in counts.items()}
    notes["dropped"] = {"sliver": dropped}
    return out, notes
