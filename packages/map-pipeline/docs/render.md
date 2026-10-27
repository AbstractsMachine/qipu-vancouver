# Render

The render stage draws each year's scene through the map's fixed camera and writes it as frames: the picture, what
surface every pixel shows, and which building. The painter turns the picture into the map; the era stage compares the
class and id passes of two years to find what changed.

```
qipu-map render --backend preview|blender [--year Y] [--samples N] [--device OPTIX|METAL|CUDA|CPU]
```

Without `--year` it renders every year that has a scene. Every year of an area uses the same canvas and frames,
planned from today's scene (`eras.today` in the city file): the era stage compares years pixel for pixel, so a past
year's lower skyline must not shrink its canvas. A year whose scene, terrain and settings have not changed since
its last finished render is skipped (`render/<year>/.stamp`).

## Inputs and outputs

In: `scene/<year>/scene.json` and the terrain file it names (`terrain.npz`). A scene without terrain is drawn on level
ground, with a warning.

Out, in `render/<year>/`:

| file | what |
|---|---|
| `frames.json` | the canvas (`left`, `top`, `width`, `height`, `metres_per_px`, camera angles) and every frame's window `{name, x, y, w, h}` in canvas pixels, plus `frame_w`, `frame_h`, `overlap_px` |
| `<name>.beauty.png` | RGB, the picture |
| `<name>.class.png` | 8-bit, each pixel a `classes.SurfaceClass` id |
| `<name>.id.png` | RGB, each pixel a building: `id = R << 16 \| G << 8 \| B` is 1 + the building's index in `scene.buildings`, 0 for none |
| `job/` | Blender backend only: the job folder (below) and one log per frame |

Frame names are `c<col>_r<row>` (`c003_r001`). Read a whole pass back with
`qipu_map.render.mosaic.load_canvas(render_dir, "beauty" | "class" | "id")`: beauty comes back as `(h, w, 3)` uint8,
class as `(h, w)` uint8, id as `(h, w)` uint32, already decoded.

## Frames

The canvas is `Canvas.around` the scene's box, tall enough for its highest roof or hill. It is cut into frames of
2048 x 1536 pixels that overlap by 64. Blender's denoiser and pixel filter look a little past a frame's edge, so the
mosaic takes each seam from the middle of the overlap, where both frames had full context. Each canvas pixel comes from
exactly one frame (`FramePlan.owned`). Frames on the right and bottom edges run past the canvas; the mosaic crops them.

## The two backends

Both put things in the same place: they go through the same `geo.camera` formulas, and the ground classes come from one
top-down grid (`ground.py`) that the preview looks up per pixel and Blender drapes over the terrain as a texture.

**preview** is plain Python (numpy and Pillow). For each pixel it walks the camera ray onto the terrain and looks up the
ground class; then it fills building faces and tree crowns far to near, shaded flat by the sun. No shadows, no windows,
hills do not hide what is behind them, trees are discs. CI, the tests and `make sample` use it.

**blender** writes a job folder and runs Blender once per frame:

```
blender --background --factory-startup --python src/qipu_map/render/blender/build.py -- render/<year>/job/job.json <frame>
```

Blender comes from `$BLENDER`, else `blender` on `PATH`, else the macOS app. The job folder holds `job.json` (canvas,
light, Cycles settings, every building as a mesh with its colours, every tree, and per frame its window and region) and
one `ground_<frame>.npz` per frame (that frame's piece of the terrain and of the ground-class grid). The job folder and
`render/blender/` are all a GPU box needs; the scripts there import nothing from `qipu_map`.

Inside Blender a frame builds only its region: the ground that can appear in the frame's window, grown by the longest
shadow the sun can cast into it. It builds the terrain mesh from the DEM, drapes the ground texture (water gets a deep
blue glossy surface), adds one object per building (walls with a window grid in the building's own coordinates, roofs
plain) and trees as linked copies of two crown shapes, sets an orthographic camera whose image is exactly the frame's
window, and renders three times:

- beauty: Cycles, the look below;
- class: flat emission of each surface's colour from `classes.CLASS_COLOURS`, one sample through each pixel's centre,
  no denoiser, Raw view. The driver maps the colours back to class ids (nearest colour);
- id: the same, with each building emitting its id colour and everything else black.

A frame whose three passes exist is skipped, so a stopped run resumes. A frame counts as done only when its files are
there: a zero exit code is not enough.

## The look, and the rules kept from the live map

The live map's V6 look, set on 25/09/2026 after side-by-side tests against real aerials:

- Clear midday: sun at elevation 50, azimuth 215 (from the city file), energy 7, slightly warm (1.0, 0.95, 0.88), a
  physical sky as fill at 0.38 and at 0.8 in reflections; AgX "Punchy", exposure -0.1. No haze, fog or vignette.
- A white city: walls from light palettes per building type, dark roofs on houses, light grey flat roofs.
- Glass by the decade a building went up: bronze and brown before 1980, green-blue and grey 1980-2009, light blue-grey
  from 2010. Painting every tower 1970s brown read wrong on new towers.
- Above 35 m a building gets a curtain-wall grid and more mirror-like glass: a tower is not a house with more floors.
- Colours come from a hash of the building id, so a building keeps its colour across runs and years.
- Cycles: 16 samples with the denoiser, adaptive sampling, 8 bounces, pixel filter 1.0 px (sharper than the 1.5 default
  at no cost).
- Ground classes are a draped texture, not polygons laid on the terrain: flat street strips crumple over hills.
- A street's `width_m` is its right-of-way, lot line to lot line. Streets with kerbs (arterial and residential) get a
  roadway in the middle and sidewalks out to the lot line, each a quarter of the width (1.5 to 6 m): a 66 ft street has a
  10 m roadway. Lanes, paths and rails are drawn at their full width.
- Only the area's box is drawn. Outside it the class is NONE and the picture is black (Blender's camera never sees the
  sky), so the painter can make it transparent. Water is only what the scene's water polygons cover.
- A rented GPU must render with OptiX. On the live run a pod whose OptiX failed fell back to CUDA and rendered some
  materials black, so `use_device` refuses rather than render under another device.

## Cost and time at city scale

The live map renders on rented GPUs, not on a laptop: a whole-city frame needs about 40 GB in one Blender process on a
Mac. On RunPod A40 cards (about $0.49 an hour), two frames at a time per card, a frame job of beauty and passes takes about
2.7 pod-minutes, so $0.023 to $0.027 per job. The whole of Vancouver is about 2 500 jobs: $60 to $70, three to four hours on
eight pods. Frames are converted on the pod and only the PNGs come back. Use EU or US-East data centres, start pods only
when the inputs are uploaded, and stop them as soon as the last file is fetched.

Measured on the West End sample (26/10/2026, one RunPod RTX A6000, 48 GB, $0.59 an hour, Blender 5.2.2 LTS Linux, OptiX,
16 samples): 5 years x 4 frames of 2048 x 1536, 20 frames in 5 min 53 s, so about 18 s a frame from launch to the last
pass on disk (about 10 s of that is Blender building the scene and writing beauty, class and id; the GPU idles while a
frame is built). The render stage of the sample costs about $0.06.

## Requirements

- preview: nothing beyond the package's core dependencies.
- blender: Blender 4.2 or later. Tested with Blender 5.2.2 LTS on macOS (CPU) for the check below.

## What is left out

The live renderer does more than this one; these parts are not ported:

- landmark models (bridges, the hand-built civic buildings and towers),
- life: cars, boats, people,
- transit, rail cars, freeways and bridge decks,
- port cranes and container stacks,
- the per-type facade kit (porches, balconies, cornices); buildings here are massing with a window grid,
- the post grade (`grade.py`); the painter works on the raw beauty pass.

## Agreement check

On 26/10/2026 one small frame (720 x 622 pixels of canvas at 25 cm, seven buildings with flat, gable and hip roofs, a
60 m and a 95 m tower, streets, a park with a pond, fourteen trees, ground rising 4 m) was rendered by both backends:
Blender 5.2.2 LTS on a Mac CPU at 8 samples, in about 4 seconds. Pixel for pixel over the canvas the class passes agree
on 98.8 % of pixels and the id passes on 99.4 %. Water, grass and roads agree exactly; the rest is building edges
(a pixel's centre versus Pillow's polygon fill) and tree crowns (cones in Blender, discs in the preview).
