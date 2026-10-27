# tiles

`qipu-map tiles` cuts the painted canvas, the era layers and the date maps into the pyramids the viewer loads, in the layout of
[tiles-format.md](../../../docs/tiles-format.md).

## Inputs and outputs

| reads | writes |
|---|---|
| `paint/<today>/canvas.png` | `tiles/today/{z}/{x}/{y}.webp` |
| `eras/<year>/layer.png` for each era year that has one (written by `qipu-map eras layers`) | `tiles/years/<year>/{z}/{x}/{y}.webp` |
| `eras/switch/<a>-<b>/dates.png` for each segment | `tiles/switch/<a>-<b>/{z}/{x}/{y}.png` |
| | `pyramid.json` and `.stamp` in each of those folders |

The date maps go through the same pyramid writer with their own encoder and reducer (`eras.datecodec`: a coarser pixel
keeps the earliest date of the four under it; empty tiles hold "never"). Pyramids of years or segments no longer in the
city file are removed. `pyramid.json` records a layer's deepest zoom, tile size, file suffix and its `have` bitmaps; the
publish stage reads it instead of scanning folders, so it only ever names tiles this stage wrote.

## How it works

`pyramid.write_pyramid` takes the whole canvas as the deepest zoom, `zmax`, the number of halvings it takes to fit in one
512 px tile. It cuts the level into tiles from the top-left, pads the edge tiles with transparent pixels, halves the
level, and repeats down to zoom 0. Halving rounds odd sizes up (the extra row or column is transparent), which gives the
level sizes the contract states: `ceil(width / 2^(zmax - z))`. A tile with no visible pixel is not written. Tiles left
over from an earlier run that this run did not write are removed, so the folder and `pyramid.json` always agree.

Each layer is keyed on the bytes of its canvas and the encoder settings (`cache.py`): re-running `tiles` after painting
one more year cuts only that year. `--force` cuts everything again.

A past year may be painted at a coarser scale than today. Its canvas must then be exactly the size of one of today's zoom
levels, so its tiles fall on the same grid; the viewer scales its deepest tiles up past that zoom.

## Rules and why

- Halve on premultiplied colour. A plain average of RGBA mixes the black of transparent pixels into the edge of the
  painting, which shows as a dark rim around the city and around every hole at the outer zooms.
- Halve the whole level at once. Halving each tile from its four children filters each child without its neighbours,
  which leaves faint seams where tiles meet.
- WebP at quality 90 with Pillow's default effort, as the painted tiles on qipu.org are made. A fully opaque tile is
  written without an alpha channel: same picture, smaller file. Only a fully opaque one: a half-empty tile saved without
  alpha turns its empty half black.
- Refuse near-black tiles, whose brightest pixel is under 12: a black square reads as a hole in the map, and the fix
  belongs upstream, in the frame or the paint pass.
- 512 px tiles drawn at 256 CSS px, so they are sharp on a 2x screen.

## Phones

Phones get the same tiles as desktops; there is no lighter phone set to build. What changes on a phone
is which zoom the viewer asks for, and that is the viewer's choice: a 1x screen takes the level below its zoom, a 2x
screen its own level, and a 3x screen one level finer only where the browser reports at least 6 GB of memory (iPhones
crash on it, so they keep the 2x level).

## Limits

- The whole canvas is held in memory, plus a float copy while halving: about 20 bytes a pixel. A district (a few
  thousand pixels square) takes well under a gigabyte. The whole of Vancouver at 0.25 m/px (about 40,000 x 25,000 px)
  would need about 20 GB. Cutting one area at a time keeps that out of the way.
- Halving with a box filter is softer than Lanczos at the outer zooms. It is the price of having no seams and no rims.

## Time

About 30 ms per tile on a laptop: a 4096 x 3072 canvas (65 tiles over five zooms) takes about two seconds.
