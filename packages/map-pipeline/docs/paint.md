# paint

The paint stage turns the render into the map's photographic skin. A diffusion model (FLUX.2 klein) repaints the render
tile by tile as an aerial photograph, keeping its geometry; the stage then joins the tiles, puts the render's water back
and writes one painted canvas per year. It is the same recipe that painted the live Vancouver map, cut down to the parts
that made it into the live tiles.

## Inputs and outputs

Reads, from `render/<year>/`:

- `frames.json` and each frame's `<name>.beauty.png` and `<name>.class.png`, through `render.mosaic.load_canvas`;
- the canvas's `left` and `top` in `frames.json`, which place the canvas in the world (see the grid below).

Writes, in `paint/<year>/`:

- `canvas.png`: the painted canvas, RGB, the size of the render canvas.
- `tiles/<digest>.png`: one PNG per model call, named by a hash of everything the call depends on. This is the cache.
- `report.json`: tiles in the grid, tiles painted, reused from the cache and re-rolled, tiles still flagged after their
  re-rolls, water tiles, tiles left as render (`--max-tiles`), half-resolution anchors painted and reused, the prompt
  keys used, and the seconds the stage took.

```
qipu-map paint --backend identity|diffusers|replay [--year Y] [--max-tiles N] [--colour-restore] [--replay-dir D]
```

`--year` defaults to the city's `today`. `--max-tiles N` paints the first N tiles (row by row) and leaves the rest as the
render, for a cheap first look on a GPU box. `--backend replay --replay-dir <tiles>` re-runs the stage from another run's
tile cache without a GPU.

## How it works

The steps, in the order `paint/run.py` runs them:

- **Pre-tone** (`pretone.py`). Three small colour fixes to the model's input, never shown on the map. Flat blue reads as
  water, so blue streets and dry ground are neutralised (the model painted streets as canals). Grey roofs lose their sky-blue
  cast (pier roofs were painted as sea). Streets get a light grain seeded by the world 64 px cell, so they read as asphalt.
- **The world grid** (`grid.py`). Tiles of 1024 px every 512 px, so each pixel is painted four times and the quilt keeps
  one. Tile positions are world pixels: the canvas pixel plus the canvas's top-left in the world (`left / m`,
  `-top / m`). A tile has the same position, seed and noise in every run, every area and every year. A tile that hangs
  over the canvas edge reads the render mirrored at the edge: black padding makes FLUX paint sea.
- **Prompt keys** (`prompts.py`, texts in `prompts/<city>_*.txt`). Chosen from the class pass, never from a drawn area. A
  tile that is 95 % water is not painted. A mostly open tile (buildings at most 8 %, open ground at least 60 %) gets a key
  that names no building, roof, street or water (`meadow`, `woods`, `beach`), or `shore` when a quarter of it is sea.
  Other tiles are `base`, or `towers` when facades fill 15 % of the tile, plus a rail clause where the render shows track.
  A past year swaps the towers clause for a period clause (before 1960: brick, stone and terracotta; after: the concrete
  towers of the 1960s and 1970s) and the open keys for a period open-ground text.
- **The shared half-resolution layer** (`anchor.py`). Anchors every 1024 px each paint the 2048 px around them, shrunk to
  1024 px, and their feathered cores are joined into one layer. It is the colour anchor: tiles that share it share their
  light and colour.
- **Each tile** gets two images: its piece of that layer, blown up to 1024 px, and its pre-toned render tile, with an
  anchored prompt ("turn image 1 ... into a crisp aerial photograph with exactly the geometry of image 2"). The render
  keeps slender towers the half-resolution pass would lose.
- **Noise** (`noise.py`). The start latents come from one world noise field, in chunks keyed by (noise key, level,
  position), so overlapping tiles start from the same noise where they overlap.
- **Guards** (`guards.py`). `vanish` catches a render building the painting dissolved into its surroundings. `invent`
  catches roof-like blobs painted on open ground or water: low chroma, far from the render's colour where the render is
  grass, leaves, sand or sea, big, thick, with straight edges. A flagged tile is re-rolled with a new noise key (`nfR1`,
  then `nfR2`), same prompt, same layer; the candidate with the lowest guard cost is kept.
- **Quilt** (`quilt.py`). Every pixel comes from one tile. In each overlap the seam is the cheapest path through a
  +-200 px band, where the cost is how much the two tiles differ plus a large cost on facades, so seams go round buildings.
  The two tiles are feathered over 12 px across the seam. Rows of tiles are joined left to right, then the rows top to
  bottom.
- **Protected surfaces** (`protect.py`). Water comes from the render, and so does anything standing in it that the class
  pass does not call land (boats, wakes, floats), with a 1 px soft rim on the shore.
- **Colour restore** (`colour.py`, `--colour-restore`, off by default). One transform over the whole canvas that gives back
  the render's contrast and saturation (FLUX drops them by 20-30 %).

## Rules kept from the live map, and why

- Content keys, never area keys: an area key painted Tudor mansions on the Jericho meadows.
- No word in a prompt for a thing that must not appear, even negated: "no roof gardens" planted roof gardens, "helicopter"
  put helicopters on flat roofs, "water" on dry tiles made ponds.
- The render's water is the map's water, and so is a ferry wake: left to the model, a straight wake became a pier lined
  with houses.
- Quilt, never average: averaging overlapping tiles painted from different noise gives see-through buildings and ghost
  towers.
- A re-roll changes the noise key. With the noise passed in, a new seed alone paints the same tile again.
- Guards aim at one defect each. A guard that pulled the whole tile toward the render's colour (a 256 px colour lock and
  the pooled restore) took the painted look away, which is why the colour restore is off by default.
- The generator runs on the CPU, so the same tile comes out the same on any GPU model.
- Reflection padding, never black.

## The tile cache

Each model call's digest covers the input pixels it reads, the prompt text, the seed, the noise key, the level and
position, and the painter's recipe (model, steps, guidance, precision). A tile's call reads its piece of the
half-resolution layer, so it also changes when a neighbouring anchor's input changes. Consequences:

- a re-run after a crash paints only what is missing;
- editing one prompt file repaints exactly the tiles whose prompt changed;
- a past year looks in the other years' `tiles/` folders first, so tiles whose input did not change are copied, not
  painted. This only helps where the past render is byte-identical to today's there; path-tracing noise between two
  renders makes most tiles miss. The live map paints past years only where a building changed and copies today's
  painted bytes elsewhere; that belongs to the era stage.

## Painters

`backends.Painter` is a small Protocol: `name`, `recipe` and `paint(request) -> RGB`.

- `identity` returns its last reference image (the render tile, the full-resolution pass) so the canvas equals the
  pre-toned render. Tests and CI use it; `make sample` uses it.
- `replay` returns tiles recorded by an earlier run, looked up by digest.
- `diffusers` (`klein.py`) is FLUX.2 klein through `diffusers.Flux2KleinPipeline`, as the live runner calls it:
  `image=[layer piece, render tile]`, 1024 x 1024, 4 steps, guidance 1.0, start latents from the world noise field, a CPU
  generator. There is no img2img strength in this pipeline: the model edits from pure noise conditioned on the
  reference images, so `paint.strength` in the city file is not used.

### Model and licence

The city file names `black-forest-labs/FLUX.2-klein-4B`, which is Apache 2.0: its outputs and fine-tunes are free to use.
The live map was painted with `FLUX.2-klein-9B`, which has the FLUX Non-Commercial License: outputs may be used, but not
to train a competing model, and "direct interactions with end users" is outside its non-commercial purpose, which may
cover a public map. Use the 9B only after reading its licence. The 4B has not been compared with the 9B side by side on our
tiles yet.

## Running it on a GPU box

On a Linux box with an NVIDIA GPU (24 GB or more), CUDA 12 and Python 3.12+:

```
git clone https://github.com/AbstractsMachine/qipu-vancouver && cd qipu-vancouver/packages/map-pipeline
pip install -e ".[paint]"
python -c "from diffusers import Flux2KleinPipeline"     # needs a diffusers release with FLUX.2 klein; else:
pip install "git+https://github.com/huggingface/diffusers"
export QIPU_MAP_WORK=/workspace/work                      # holds <city>/<area>/render/<year>/ from the render stage
export HF_TOKEN=...                                        # only for a gated model (the 9B); the 4B is open
qipu-map paint --backend diffusers --area west-end --max-tiles 4    # a look at four tiles first
qipu-map paint --backend diffusers --area west-end
```

Copy back `paint/<year>/` (canvas, tiles and report). The cache means a box that dies mid-run loses at most one tile.

Expected speed, per 1024 px tile (one tile = two model calls, plus about a quarter of an anchor):

| card | klein-9B | klein-4B |
|---|---|---|
| RTX 5090 | 9.6 s (measured, FP8) | about 3-5 s (estimate) |
| RTX 4090 | 16 s (measured) | about 5-8 s (estimate) |
| L40 / L40S | about 14-18 s (estimate) | about 5-8 s (estimate) |
| RTX A6000 | | 13.6-18.2 s all in (measured, bf16) |

This code loads the model in bf16. The 9B in bf16 does not fit in 24 GB; the live runs used FP8 on a 32 GB 5090.

The A6000 row is the whole West End sample (26/10/2026, RunPod, $0.59 an hour, about 18 GB of GPU memory): five years of
40 tiles each, with 30 anchors per year, the model loaded once per year and 9 to 22 re-rolls per year. Today took 544 s,
the past years 621 to 728 s (they trip the guards more often). Painting the five years took 55 minutes, about $0.54;
the whole `qipu-map sample` run on the GPU took 62.5 minutes, about $0.62 of card time. The run with setup (venv, Blender,
model download), a four-tile smoke test and the copy back cost $1.11.

## Cost

Per km² of ground at the city file's 0.25 m/px: a 512 px stride step covers 128 m across and 128 m / sin(30.7°) = 250 m
along the view, about 32,000 m², so about **31 tiles and 8 anchors per km²**, plus the band that tall buildings add at
the top of the canvas.

| | $ per tile, all in (anchors, re-rolls, idle) | $ per km² at 0.25 m/px |
|---|---|---|
| Vancouver, measured (klein-9B, 5090) | $0.008 | about $0.25 |
| San Francisco, measured (klein-9B, 5090) | $0.0026 | about $0.08 |

The measured numbers come from the live runs (cloud cost log, 24 Sep to 25 Oct 2026). The live map's deepest level was
finer than this repository's 0.25 m/px (about 0.115 m/px), so it had about 4.7 times as many tiles per km²: Vancouver
today was about 24,000 tiles. The West End sample area is about 30 tiles, a few cents.

## Limits

- The whole canvas and every painted tile are held in memory. Fine for an area; a whole city needs the quilt streamed by
  tile rows, as the live runner did.
- There is no glass class in the class pass, so big glass towers are not taken from the render. The prompt asks for opaque
  glass instead (the `towers` clause), as the live map's last recipe did. `protect` takes a `keep` mask if a glass pass
  is added.
- `towers` is decided from the share of facades in a tile. The live map used a hand-drawn downtown polygon for it.
- The guards' thresholds were calibrated on the live map's tiles at its resolution. At 0.25 m/px a building is about half
  as many pixels across; check the thresholds on a sample before trusting the re-roll counts.
- The noise field is drawn with numpy's generator, not torch's: same property, different numbers, so a tile is not
  byte-identical to the live tile at the same place.
- Left out from the live code: the per-building facade colour correction (it needs the building colour table), the
  landmark patches (cut out, painted with their own photos, pasted back), the quay and green-roof fixes (rejected or
  unfinished on the live map), and the two-card split of one window.
