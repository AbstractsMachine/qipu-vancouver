"""Where each stage reads and writes, in one place. Every stage writes only into its own folder.

<work>/<city>/<area>/ingest/                normalised open data (GeoJSON in degrees), LiDAR grids, evidence/,
                                            sources.json
<work>/<city>/<area>/scene/<year>/          scene.json and terrain.npz
<work>/<city>/<area>/render/<year>/         frames.json and each frame's beauty, class and id images
<work>/<city>/<area>/paint/<year>/          canvas.png, the painted-tile cache tiles/, report.json
<work>/<city>/<area>/eras/<year>/           layer.png: the painted year where it differs from today
<work>/<city>/<area>/eras/switch/<a>-<b>/   dates.png: when each pixel changes from year a to year b
<work>/<city>/<area>/tiles/                 the pyramids (today/, years/<year>/, switch/<a>-<b>/) and manifest.json
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkDir:
    """Where each stage of one city and area reads and writes under the work folder."""

    root: Path
    city: str
    area: str

    @property
    def base(self) -> Path:
        return self.root / self.city.replace("/", "-") / self.area

    @property
    def ingest(self) -> Path:
        return self.base / "ingest"

    def evidence(self, name: str) -> Path:
        return self.ingest / "evidence" / f"{name}.npz"

    def scene(self, year: int) -> Path:
        return self.base / "scene" / str(year)

    def scene_file(self, year: int) -> Path:
        return self.scene(year) / "scene.json"

    def terrain(self, year: int) -> Path:
        return self.scene(year) / "terrain.npz"

    def scene_years(self) -> list[int]:
        """The years that have a scene, oldest first."""
        root = self.base / "scene"
        if not root.is_dir():
            return []
        return sorted(int(p.name) for p in root.iterdir() if p.name.isdigit() and (p / "scene.json").is_file())

    def render(self, year: int) -> Path:
        return self.base / "render" / str(year)

    def frames(self, year: int) -> Path:
        return self.render(year) / "frames.json"

    def paint(self, year: int) -> Path:
        return self.base / "paint" / str(year)

    def canvas(self, year: int) -> Path:
        return self.paint(year) / "canvas.png"

    def paint_tiles(self, year: int) -> Path:
        return self.paint(year) / "tiles"

    def paint_report(self, year: int) -> Path:
        return self.paint(year) / "report.json"

    def eras(self, year: int) -> Path:
        return self.base / "eras" / str(year)

    def layer(self, year: int) -> Path:
        return self.eras(year) / "layer.png"

    def switch(self, a: int, b: int) -> Path:
        return self.base / "eras" / "switch" / f"{a}-{b}"

    def dates(self, a: int, b: int) -> Path:
        return self.switch(a, b) / "dates.png"

    @property
    def tiles(self) -> Path:
        return self.base / "tiles"

    def today_tiles(self) -> Path:
        return self.tiles / "today"

    def year_tiles(self, year: int) -> Path:
        return self.tiles / "years" / str(year)

    def switch_tiles(self, a: int, b: int) -> Path:
        return self.tiles / "switch" / f"{a}-{b}"

    @property
    def manifest(self) -> Path:
        return self.tiles / "manifest.json"
