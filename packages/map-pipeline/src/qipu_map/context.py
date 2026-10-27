"""What every command needs: the city, the area and the work folder."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from qipu_map.config import City, load_city, work_root
from qipu_map.geo.boxes import GeoBox, WorldBox
from qipu_map.geo.camera import ObliqueCamera
from qipu_map.geo.projection import LocalProjection
from qipu_map.paths import WorkDir


@dataclass(frozen=True)
class Context:
    city: City
    area: str
    work: WorkDir

    @property
    def projection(self) -> LocalProjection:
        return LocalProjection.from_config(self.city.projection)

    @property
    def camera(self) -> ObliqueCamera:
        return ObliqueCamera.from_config(self.city.camera)

    @property
    def bbox(self) -> GeoBox:
        """The area in degrees."""
        return self.city.area(self.area).bbox

    @property
    def box(self) -> WorldBox:
        """The area in local metres."""
        return self.projection.box_to_world(self.bbox)


def add_common(parser: argparse.ArgumentParser, *, explicit: bool = False) -> None:
    """--city, --area and --work. With `explicit` (publishing), city and area have no default and must be given."""
    city_default, area_default = (None, None) if explicit else ("vancouver", "west-end")
    parser.add_argument(
        "--city", default=city_default, required=explicit, help="a city file name in qipu_map/cities, or a path to one"
    )
    parser.add_argument("--area", default=area_default, required=explicit, help="an area named in the city file")
    parser.add_argument("--work", type=Path, default=None, help="work folder (default: $QIPU_MAP_WORK or ./work)")


def context_from_args(args: argparse.Namespace) -> Context:
    city = load_city(args.city)
    city.area(args.area)  # raises StageError for an area the city file does not name
    return Context(city=city, area=args.area, work=WorkDir(work_root(args.work), city.id, args.area))
