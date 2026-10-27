# Architecture

The pipeline turns open data about a city into a painted bird's-eye map that can be played through time. It has seven
stages. Each one reads files the previous one wrote, writes its own files into one folder, and can be run, cached and tested
on its own.

```
 open data                                                                          object storage
 (City of Vancouver, OSM, LiDAR)                                                    (S3, Cloudflare R2)
      │                                                                                   ▲
      ▼                                                                                   │
  ┌────────┐  layers   ┌───────┐  today's  ┌─────────┐ scene  ┌────────┐ frames ┌───────┐ canvas ┌───────┐ pyramids ┌─────────┐
  │ ingest │──────────▶│ scene │──scene───▶│  eras   │──per──▶│ render │───────▶│ paint │───────▶│ tiles │─────────▶│ publish │
  └────────┘ GeoJSON,  └───────┘           │ (before)│  year  └────────┘ beauty,└───────┘ RGB(A) └───────┘          └─────────┘
             LiDAR                         └─────────┘         Blender or class, AI model or          ▲   manifest.json
             grids                              │              preview    id     identity            │
                                                │                                   │                 │
                                                │   past-year canvases, date maps   ▼                 │
                                                └─────────────────────────────▶ ┌─────────┐ layers ───┘
                                                                                 │  eras   │
                                                                                 │ (after) │
                                                                                 └─────────┘
```

| stage | reads | writes | runs on |
|---|---|---|---|
| `ingest` | open-data APIs (or a saved raw folder) | `ingest/*.geojson`, `dsm.npz`, `dem.npz`, `sources.json` | laptop, network |
| `scene` | the ingest layers | `scene/<today>/scene.json`, `terrain.npz` | laptop |
| `eras scene` | today's scene, the city's era rules | `scene/<year>/scene.json` for each past year | laptop |
| `render` | a scene | `render/<year>/frames.json`, per frame `beauty`, `class` and `id` images | Blender on a GPU, or the CPU preview |
| `paint` | the render's frames | `paint/<year>/canvas.png` and a tile cache | a CUDA GPU, or the identity painter |
| `eras layers` | painted canvases and id passes of every year | `eras/<year>/layer.png`, `eras/switch/<a>-<b>/dates.png` | laptop |
| `tiles` | today's canvas, the era layers and date maps | `tiles/today/`, `tiles/years/<year>/`, `tiles/switch/<a>-<b>/` | laptop |
| `publish` | the tiles and the render's canvas | `tiles/manifest.json`, `ground.json`, uploaded release | laptop, network |

## Ideas the design rests on

**Blender owns the truth, the AI owns the look.** What exists, where, how tall and since when is decided by data and code
before anything is painted. The model only repaints the surface of a render it is given, tile by tile, and the stages around
it check that it did not invent or remove anything (a building that vanished, a pier drawn on open water). This is why the
3D scene exists at all: an image model asked for "Vancouver in 1950" draws a plausible city, not the one that stood there.

**One camera, one canvas.** The map is an orthographic view looking north and 30.7° down. `geo/camera.py` defines it once;
the renderer's camera, the preview rasteriser, the paint grid, the era date maps, the tile pyramid and the viewer's pins all
go through the same two lines of arithmetic, so they line up to the pixel. A building's height moves its roof up the image,
which is why pins need a ground height (see [docs/tiles-format.md](../../docs/tiles-format.md)).

**A past year is today minus what did not exist yet.** The open data describes the city now. Each building carries its year
built and where that year comes from (a tax roll, a permit, OSM, or a stated convention). A past scene keeps what stood then
and adds stand-ins only where a dated record or an aerial photo says something was there. Rules say whether they are
sourced or a convention, and a convention never overrides a record.

**Play changes one building at a time.** Between two painted years, a date map says when each pixel switches. Pixels of a
building take that building's own year, so during playback the city grows in the order it was built instead of jumping at
the key years.

**Same inputs, same bytes.** Seeds come from a tile's position on the canvas, iteration is sorted, outputs carry no
timestamps. Each stage keys its output on a hash of its inputs and parameters and skips work whose key has not changed;
the painter does the same per tile, which is what makes re-running a city after a fix cheap.

**The expensive stages have stand-ins.** Blender and the image model need a GPU. The `preview` renderer (a small rasteriser
in numpy) and the `identity` painter produce the same files from the same inputs on any machine, so the whole chain runs in
CI and on a laptop, and every stage after them is tested on real outputs.

## Code layout

```
src/qipu_map/
  config.py, cities/       city settings (TOML): projection, camera, eras, paint recipe, areas, publishing
  model.py                 the scene: buildings, streets, trees, parks, water, terrain
  geo/                     projection (degrees to metres) and the oblique camera and canvas
  classes.py               the surface classes of the render's class pass
  paths.py, cache.py       where files go; skip work whose inputs did not change
  ingest/ scene/ render/ paint/ tiles/ eras/ publish/    one package per stage, each with a `command.py`
  cli.py, sample.py        the `qipu-map` command and the sample run
```

Each stage package keeps I/O at its edges: the logic (height from LiDAR, roof form, building type, frame planning, paint
grid, blending, date maps, pyramid maths) is pure functions over arrays and dataclasses, and is unit-tested on small
fixtures. `tests/integration/` runs stages together on the sample area.

## Where this comes from

This is the curated core of the code that made qipu.org's Vancouver and San Francisco maps in September and October
2026. That code grew run by run; what is here is the part on the path from open data to published tiles, rewritten as
small typed modules. A rule was kept when it fixed something seen on the published map, and its comment says what it
fixes. Numbers marked "measured" (run times, costs, thresholds) come from those runs.

## What the qipu.org map has that this repository leaves out

The qipu.org map is made by the same chain with more on top. Left out here, on purpose, because each one is
city-specific, experimental, or operations rather than mechanism:

- hand-modelled landmarks (Canada Place, Harbour Centre, the bridges) and their painted patches;
- moving life: cars, boats and their wakes, people;
- the scripts that hire and watch rented GPUs, stage inputs in object storage and pull outputs back;
- per-area fixes found in review (for example north False Creek before Expo 86);
- the whole-city "quarters" format of the site, where detailed areas are drawn over a coarser city layer.
