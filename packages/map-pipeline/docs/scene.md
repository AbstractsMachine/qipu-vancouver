# scene

The scene stage turns the ingested open data into today's city in 3D: every building with its ground, height, roof form
and type, the trees, the streets, the parks, the water and the land, and the terrain under them. Nothing is drawn here;
the renderer draws the scene and the eras stage derives the past years from it.

## Inputs and outputs

`qipu-map scene [--force]`, after `ingest`:

| reads (`ingest/`) | writes (`scene/<today>/`) |
|---|---|
| `buildings.geojson`, `dsm.npz`, `dem.npz` (required) | `scene.json` (`model.Scene`, format `qipu-scene/1`) |
| `trees.geojson`, `streets.geojson`, `parks.geojson`, `water.geojson` (optional) | `terrain.npz` (the DEM cropped to the area, no-data as 0 m) |

The stage is skipped when the stamp in `scene/<today>/.stamp` matches the hash of its inputs, the area box and
`RULES_VERSION` in `scene/command.py`; `--force` rebuilds anyway. The output is deterministic: buildings, trees and
polygons are sorted, conventional choices are drawn from a hash of the building id, and nothing carries a timestamp.

`scene.json`'s `notes` counts how each decision was made (height sources, roof sources, type rules, slivers dropped,
street and canopy trees), so a run can be checked at a glance.

The West End sample (304 footprints, 769 register trees) builds in under 2 seconds on a laptop.

## How it works

**Footprints** are made valid, holes are dropped (the model has none), the largest part of a multi-part outline is kept,
points closer than 5 cm are merged and the outline runs counter-clockwise. Buildings that touch the area box are kept
whole.

**Heights** are measured from the LiDAR: the height above ground (DSM minus DEM of the same survey, so the
vertical datum cancels) of every 1 m cell inside the footprint drawn 1 m in, because walls and eaves read half ground.
A flat-roofed building stands to the median; a pitched one to the 95th percentile, its ridge. The guards, each against
a misreading seen on Vancouver's data:

- under 12 cells is too few to trust;
- over 15 % of the cells empty: the 2025 survey left the tops of tall towers empty and a median read at their edges came
  out about 40 m too low, so the record wins, unless the reading is higher than the record (empty cells only pull a
  reading down, so a rise is real);
- a median under 2 m is a vacant lot or a demolished building in the survey;
- a record of 12 m or more that the median undercuts while the 90th percentile still reaches 80 % of it is a tower over
  a podium: the record wins.

When the LiDAR cannot be used, the height is OpenStreetMap's `height`, else `building:levels` at 3.2 m a storey, else the
type's default height. A building's ground is the mean of the terrain under its corners.

**Towers on podiums.** The City traced one outline for a tower and its podium. When the type rules call an outline a
tower on a podium (below), the tower becomes its own building (`<id>-tower`) on the cells that stand above halfway
between the median and the 90th percentile; the podium keeps the median. Without this the tower vanishes, or the podium
becomes a slab the size of a block.

**Roof forms** come from the DSM over the footprint drawn 0.5 m in. Per cell the surface's slope; cells on a step
(more than 0.45 m off the mean of their eight neighbours: an edge, a parapet, the ridge line, a branch) are left out.
The roof is flat when 45 % of the kept cells are level (under 9°) or less than 45 % are pitched (14° to 62°). Otherwise
three models are fitted by least squares, refitted without the outlying cells, on the footprint's minimum-area rectangle, `z = eave + k · d(p)` with
`d` the distance to the eave line: a gable along the long side, a gable across it, and a hip; the ridge may slide a
metre either way, since the footprints and the survey are years apart. A hip has to fit at least 15 % better than the
better gable, because at 1 m a house's roof faces are 3 to 5 cells wide and the two are easy to confuse. A low pitch
that the slope rule calls flat (the 1960s-80s houses' 3-4:12 roofs) counts as pitched when a roof model fits it twice
as well as a level plane at 8° or more. The roof is left to the type when there are under 20 cells, more than 35 % of
them are empty, the surface is too rough, or one sloping plane fits best (a shed roof, which the scene has no form for).

**Types** decide the pitch and, later, the look. The rules are the ones the Vancouver map was made with, adapted to what
ingest provides: the use is the parcel's zoning district from the tax roll or the OpenStreetMap building tag. The first
rule that matches wins:

| rule | type | why |
|---|---|---|
| tower on a podium | podium tower (+ point tower) | 90th percentile 32 m or more and the median under 60 % of it: one outline holds a tower over a low base |
| tower | point tower | 32 m is about ten storeys: nothing else in the city is that tall |
| industrial | industrial | industrial zones (I-, M-, IC-) and tags, over 150 m² so a shed in a works yard stays a shed |
| outbuilding | shed | under 30 m² or under 3.2 m, or tagged garage or shed |
| laneway house | laneway house or shed | under 90 m² and 8.5 m with a building twice its size within 25 m: a laneway house from 4.8 m, else a garage |
| civic | civic | schools, churches, halls, hospitals and hotels by their tag |
| big low building in a house zone | civic | 700 m² or more in a single-family zone is a school, church or hall |
| house | character house, Vancouver Special or modern house | house zones (RS, RT, R1...) and tags, or an unzoned footprint under 450 m² and 12 m; by period |
| shops and offices | commercial or mid-rise | commercial zones (C-, HA-, DD...): under 12 m commercial, else a mid-rise |
| apartments | walk-up, row house, mid-rise, point tower or character house | everything else, by period and height |

Inside the house rule: before 1946 a character house; 1965 to 1985 a Vancouver Special when it is a two-storey box
(5.5 to 10 m, at least 100 m², filling 84 % of its rectangle) with a flat or low (up to 30°) roof; otherwise a modern
house. Inside the apartments rule: before 1946 a flat-roofed block of 8 m or more is a walk-up and anything else a
character house cut into suites; 1946 to 1979 a mid-rise from 17 m, a walk-up from 7.5 m; from 1980 a row house under
10.5 m when pitched (or, from 2006, under 600 m²), a walk-up (1980-2005) or mid-rise (2006 on) under 22 m, else a point
tower. A building with no year is typed as if built in 1925 when its roof is pitched 35° or more (a pre-war character house's
roof) and 1975 otherwise; that guess only picks the type and is never written out as its year.

When the LiDAR could not read a roof, the type's usual roof is used: character houses, Specials, laneway and row houses
get a gable (a hip for about a third of them, drawn from the id), modern houses a hip, everything else a flat roof.

**Sliver rule.** A footprint under 30 m² that stands taller than three times its side is dropped: such a record is a
misread (a 7 m² "single family" record read at 35 m would stand as a brick chimney in a park).

**Massing** (`scene/massing.py`, shared with the renderer) turns a building into a closed mesh. Walls stand on the
footprint from 0.6 m below the ground (so a gentle slope never shows a gap) to the roof line. A flat roof caps the top.
A pitched roof is a height field over the footprint on its minimum-area rectangle: a gable rises from both long eaves to
a ridge (across the short side on a Vancouver Special, whose side gable faces the neighbours), a hip from all four
sides. The pitch is the type's (42° for a character house, 16° for a Special); the roof never takes more than 55 % of
the building's height. Pitched roofs are drawn only on footprints up to 800 m² and buildings under 25 m, because on
anything bigger a gable reads as a barn. A box-shaped house is 12 triangles with a flat roof, 18 with a
gable and 42 with a hip.

**Trees.** Register trees keep their position, genus and height (8 m when the register has none); the crown is
`a + b · DBH` (inches), capped, with the Vancouver map's values for broadleaf and conifer. Conifers and palms are told
apart by genus. Canopy crowns, for the yards, parks and woods the register does not list, come from the DSM:
cells over 2.5 m above ground and not on a building (grown by a metre), opened by one cell to drop poles and wires,
smoothed, their local maxima as tree tops with a window that grows with the height; each crown's width comes from the
canopy cells nearest its top. A crown within 2.5 m of a register tree is that tree.

**Ground.** Streets keep their width, or take a default by kind (arterial 15 m, residential 9 m, lane 6 m, path 3 m,
rail 4 m) and are clipped to the box with a street's width of margin. Parks and water are clipped to the box; the land
is the box minus the water. Outer rings run counter-clockwise, holes clockwise.

## What the qipu.org map does that this stage leaves out

- Hand-modelled landmarks (bridges, the Marine Building, the stadiums), placed by hand.
- The second survey: the qipu.org heights compare the 2016 and 2025 surveys building by building (rebuilt, grew, canopy,
  split); here there is one survey and the OSM height plays the record.
- The land-cover raster that tells the qipu.org canopy step where trees are and whether they are conifers. Here any
  tall, unbuilt, crown-shaped surface counts, and a crown much taller than wide is called a conifer.
- LiDAR point-cloud crown shapes, roof colours, per-building facades, party walls and shed, sawtooth and barrel roofs.
- The parcel join for the laneway rule: the qipu.org map knows which building is a parcel's main one; here "a building
  twice the size within 25 m" stands in for it.

## Limits

- A footprint keeps one ground height. On a steep street the low side of a long building can float above the terrain
  by more than the 0.6 m foot.
- The ridge of a measured gable follows the footprint's long side (or the type's rule); the fitted ridge direction is
  not carried into the scene, so a side-gabled house the type rules do not catch gets a front gable.
- A tower over a podium gets one tower: a podium holding two towers keeps only the larger.
- A pitched roof over an L-shaped footprint is measured from the bounding rectangle, so the inner corner's eave sits
  higher than the outer ones.
- Pitched roofs are cut along their creases triangle by triangle. On a detailed footprint that is wasteful: the West
  End's hipped houses have a median of 130 triangles where about 30 would do.
