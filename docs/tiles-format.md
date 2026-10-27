# Tile format

The contract between the map pipeline (`packages/map-pipeline`, which writes and publishes the tiles) and the viewer
(`packages/viewer`, which shows them). Version `qipu-tiles/1`.

A release of one city or area is a folder of images and one `manifest.json`. The viewer reads the manifest first and
needs nothing else to show the map at any year, place pins on it, and credit the sources.

## The picture is oblique, not a web map

The map is a painted bird's-eye view, as if seen from a plane to the south looking north and down at about 31°. It is not
in Web Mercator: a tile is a square of an oblique picture, and a building's roof sits up the image from its footprint by its
height. So the viewer uses a plain pixel coordinate system (Leaflet's `CRS.Simple`, OpenLayers' pixel projection, or
MapLibre with a custom source), and converts places to pixels with the matrix in the manifest.

## Layout

```
<base>/manifest.json
<base>/today/{z}/{x}/{y}.webp                 the map today
<base>/years/<year>/{z}/{x}/{y}.webp           a past year, transparent where it looks like today
<base>/switch/<from>-<to>/{z}/{x}/{y}.png      when each pixel changes between two years
<base>/ground.json                             ground height, to place pins (optional)
```

`<base>` is the release folder, for example `https://tiles.qipu.org/ca/vancouver/city/r20261026`. Paths in the manifest
are relative to it.

## Canvas and zoom levels

- The canvas is the picture at the deepest zoom, `zmax`: `canvas.width` x `canvas.height` pixels, `canvas.metres_per_px`
  metres per pixel across the image.
- Zoom `z` halves the picture `zmax - z` times: its size is `ceil(width / 2^(zmax - z))` by `ceil(height / 2^(zmax - z))`.
  Zoom 0 is the first level that fits in one tile.
- Tiles are `tile_size` (512) pixels square. Tile `(x, y)` at zoom `z` covers pixels `[x*512, (x+1)*512)` by
  `[y*512, (y+1)*512)` of that level, with x to the right and y down. Edge tiles are full size; pixels past the canvas are
  transparent in the WebP layers and hold "no change" (65535) in the date maps.
- A layer may stop before `zmax` (the past years are painted at a coarser level). Above its own `zmax` the viewer scales its
  deepest tiles up.
- A tile that is not listed in the layer's `have` does not exist; the viewer does not request it. Missing tiles are
  transparent. A zoom level missing from `have` has no tiles at all.

### `have`

Per zoom level, a bitmap of the tiles that exist, so the viewer never asks for a tile that is not there:

```json
"have": {"3": {"x0": 1, "y0": 0, "cols": 6, "rows": 4, "bits": "/38P"}}
```

Bit `i = (y - y0) * cols + (x - x0)` is set when tile `(x, y)` exists. Bits are packed eight to a byte, most significant bit
first, and the bytes are base64-encoded. (The qipu.org site's older index packs them least significant bit first; a viewer
ported from it must flip the order.)

## Images

| layer | file | pixels |
|---|---|---|
| `today` | WebP, RGBA | the painted map; alpha 0 outside the painted area. A tile written without an alpha channel is fully opaque |
| `years/<year>` | WebP, RGBA | that year where it differs from today; alpha 0 where the viewer should show `today` |
| `switch/<from>-<to>` | PNG, 8-bit RGB | the date each pixel changes from `<from>` to `<to>`, encoded below |

### Date maps (`switch`)

Each pixel holds a date `d` as a 16-bit number `n = R * 256 + G`:

- `d = 1800 + n / 100` (a decimal year: 1961.5 is the middle of 1961);
- `n = 65535` means the pixel does not change in this segment;
- `B` is always 0.

Date maps are read with nearest-neighbour sampling, never interpolated. A pixel at a coarser zoom holds the earliest date of
the four pixels under it, so nothing appears late when zoomed out.

## Showing a year

The manifest lists the past years `K1 < K2 < ... < Kn` and the year of `today`, `T`. To show the map at a year `Y` (any
decimal year):

1. If `Y >= T`, show `today`.
2. If `Y <= K1`, show `today` with `years/K1` over it.
3. Otherwise find the segment `A <= Y < B`, where `B` is the next past year or `T`. For each pixel, with `d` from
   `switch/A-B`: show `B` if `d <= Y`, else `A`. "Show `Kn`" means `today` with `years/Kn` over it; "show `T`" means `today`.

So during playback each building appears in the year it was built, not all at once at the next key year. A viewer without
WebGL can skip the date maps and switch whole layers at the key years.

## Placing things on the picture

A place is given in degrees (longitude, latitude) and, if known, its ground height `h` in metres.

1. Degrees to local metres, with `projection`: `x = (lon - lon0) * metres_per_degree * cos(lat0)`,
   `y = (lat - lat0) * metres_per_degree`.
2. Local metres to canvas pixels at `zmax`, with the 2x4 matrix `world_to_px`: `[px, py] = world_to_px @ [x, y, h, 1]`.
3. At zoom `z`, divide by `2^(zmax - z)`.

The ground height matters: on this camera 10 m of height moves a point about 34 pixels up the canvas at 0.25 m/px. When the
place has no height, sample `ground.json`:

```json
{"x0": -1200.0, "y0": 3600.0, "cell": 25.0, "cols": 40, "rows": 30, "decimetres": [123, 125, ...]}
```

It is a north-up grid in local metres: the value for row `i` (going south), column `j` (going east) is
`decimetres[i * cols + j] / 10` metres, for the cell whose top-left corner is `(x0 + j * cell, y0 - i * cell)`. Sample it
bilinearly at the cell centres. Cells with no ground data (open water past the survey) hold 0, sea level.

## manifest.json

```json
{
  "format": "qipu-tiles/1",
  "city": "ca/vancouver",
  "area": "west-end",
  "release": "r20261026",
  "tile_size": 512,
  "canvas": {"width": 2390, "height": 1720, "metres_per_px": 0.25, "zmax": 3},
  "camera": {"azimuth_deg": 0.0, "elevation_deg": 30.709},
  "projection": {"kind": "local-equirectangular", "lon0": -123.1302, "lat0": 49.2565, "metres_per_degree": 111320.0},
  "world_to_px": [[4.0, 0.0, 0.0, 5650.1], [0.0, -2.0428, -3.4396, 6700.3]],
  "today": {"year": 2026, "path": "today/{z}/{x}/{y}.webp", "zmax": 3, "v": "3f9a1c2e", "have": {}},
  "years": [
    {"year": 1950, "path": "years/1950/{z}/{x}/{y}.webp", "zmax": 3, "v": "8b0e44d1", "have": {}}
  ],
  "switch": [
    {"from": 1950, "to": 2026, "path": "switch/1950-2026/{z}/{x}/{y}.png", "zmax": 3, "v": "c2d9e0aa", "have": {}}
  ],
  "ground": "ground.json",
  "attribution": [
    "Contains information licensed under the Open Government Licence – Vancouver.",
    "© OpenStreetMap contributors (ODbL)."
  ]
}
```

- `years` is sorted by year, `switch` by `from`; there is one switch entry for each consecutive pair, the last one ending at
  `today.year`.
- `v` is a short hash of the layer's tiles. Append it to tile URLs (`?v=3f9a1c2e`) so caches pick up a re-published layer.
  Tiles are served with `Cache-Control: public, max-age=300` by default, the manifest with `max-age=60`. A viewer that
  always appends `v`, as the qipu viewer does, lets the publisher cache tiles as
  `public, max-age=31536000, immutable` instead (the city file's `publish.cache_control`; see the pipeline's
  `docs/publish.md`).
- Fields not listed here may be added in later minor versions; a viewer ignores what it does not know. A breaking change
  bumps `format`.

## Differences from the qipu.org tiles

The qipu.org site predates this contract and reads an older, richer index (`render/index.json` and `render-years.json`):
several detailed areas ("quarters") drawn over a coarser whole-city layer, each with its own past years. `qipu-tiles/1` is
that format for one area at a time, with the same date-map encoding and the same tile grid. The pipeline in this repository
writes `qipu-tiles/1`.

## How the viewer reads it

`packages/viewer` reads two formats into one model (`src/tiles/painting.ts`): a frame in level-0 CSS pixels (a tile is
`tile_size` image pixels shown at 256 CSS pixels), the present pyramid, the eras, and a function from local metres to the frame.

- **qipu-tiles/1** (`src/tiles/qipu-tiles.ts`): the frame is the canvas at `zmax` divided by `2^zmax` and by `tile_size / 256`;
  `world_to_px` is used as it is. The past is one area covering the canvas, keys `years[*]` then `today`, switch maps decoded
  literally (`n = 0` is 1800.00, `B` unused). Before the first past year the viewer shows that year, as step 2 above says.
  `have` is read most significant bit first, and a level missing from it has no tiles.
- **The live qipu.org index** (`src/tiles/live-index.ts`, `src/tiles/live-eras.ts`): `render/index.json` gives the renderer's
  reference camera (`ref`, `dpr`, `tile`, `levels`, `proj.sA`, `proj.zex`) and an optional `have` packed least significant bit
  first as `[x0, y0, cols, bits]`; `_preview_eras/render-years.json` gives `now`, `years`, `min`, `public` and `quarters`, areas
  with a box in level-9 image pixels (`l9`), their own key years and switch maps. Its switch maps are `c3c` or `c3d` (`n = 0`
  means the segment's midpoint; blue's low 4 bits a fade of 0.0015 * 2^(w-1) years, its high 4 bits, for `c3d`, a lead in
  `leadStep` years during which a `clear` pyramid, the cleared site, shows) or, without `enc`, the older form whose blue is a fade
  in 0.005-year steps. Before an area's first key year the area shows nothing and the present shows through.

Both formats share the grid (tile `(x, y)` at zoom `z` covers `[x*tile, (x+1)*tile)` image pixels of that level), the date code
`(year - 1800) * 100` in red and green, and 65535 for "does not change".
