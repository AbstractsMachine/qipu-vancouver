"""Built-up masks from period air photos, for the eras stage's stand-ins.

A raw `<name>_built.npz` holds `share` (uint8, 0 = open ground, 255 = fully built; 0 also where the photo does not
cover), and the grid's north-west corner `x0`, `y0` and `cell` in local metres. It becomes `evidence/<name>.npz`, a
`model.Raster` of shares from 0 to 1, which `eras` reads for the years the photo speaks for.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from qipu_map.ingest.raw import RawStore
from qipu_map.model import Raster

SUFFIX = "_built.npz"


def write_evidence(store: RawStore, out: Path) -> list[str]:
    """Convert every built-up mask in the raw folder; returns the names written, sorted."""
    names = []
    for path in sorted(store.root.glob(f"*{SUFFIX}")):
        name = path.name.removesuffix(SUFFIX)
        with np.load(path) as z:
            raster = Raster(float(z["x0"]), float(z["y0"]), float(z["cell"]), z["share"].astype(np.float32) / 255.0)
        (out / "evidence").mkdir(parents=True, exist_ok=True)
        raster.save(out / "evidence" / f"{name}.npz")
        names.append(name)
    return names
