# eras

The map has a time slider. Press Play and the city goes back to its earliest era year, then runs forward: houses go up
one by one in the year the tax roll says they were built, bridges open in their year, towers replace the houses that stood
on their lots, and the ground between them changes slowly over each stretch of years. The eras stage makes what that
needs: the scene of each past year, before rendering, and after painting, each year's layer and the date maps that say
when every pixel switches from one year to the next.

## Inputs and outputs

`qipu-map eras scene [--year Y]`, after `scene` and before `render`:

| reads | writes |
|---|---|
| `scene/<today>/scene.json`, `terrain.npz` | `scene/<year>/scene.json` for each era year (or the one given), and a copy of `terrain.npz` |
| `eras/rules/<city>.toml` (or `--rules`) | |
| `ingest/evidence/<name>.npz`, optional | |

`qipu-map eras layers`, after `render` and `paint` have run for today and every era year, and before `tiles`:

| reads | writes |
|---|---|
| `paint/<year>/canvas.png` for today and each era year | `eras/<year>/layer.png` for each era year: RGBA, the year where it differs from today, alpha 0 elsewhere |
| the render's `class` and `id` passes of every year (through `render.mosaic.load_canvas`) | `eras/switch/<a>-<b>/dates.png`, one per segment, in the date maps' tile encoding |
| `scene/<year>/scene.json`, today's scene | a `.stamp` next to each, keyed on its inputs, the rules and the seed |

The segments are consecutive era years, the last one ending at today: with eras 1930, 1950, 1972 and 1982 they are
1930-1950, 1950-1972, 1972-1982 and 1982-2026. The stage writes only into `eras/`; `qipu-map tiles` cuts each
`layer.png` into `tiles/years/<year>/` and each `dates.png` into `tiles/switch/<a>-<b>/`. An output whose inputs did not
change is skipped (`--force` rebuilds it).
The date maps follow the encoding in [tiles-format.md](../../../docs/tiles-format.md): `n = R * 256 + G`, the date is
`1800 + n / 100`, 65535 means the pixel does not change, B is 0; a coarser zoom keeps the earliest of the four pixels
under it, and padding past the canvas holds 65535.

## The rules

A past scene is today's scene with rules applied. Each rule is one of two kinds, and the rules file says which.

- **Sourced**: a date read from a dated record. A building stands from its tax-roll year built and is gone from its
  lot's demolition permit date. Bridges, viaducts and rail lines take their opening and closing years from the rules
  file, matched by name or id (Vancouver's come from Wikidata and TransLink).
- **Convention**: a period choice made where no record speaks. It may fill a gap; it never contradicts a record.

The conventions Vancouver uses:

- An undated building (a school, a park building: 2,572 of them) takes the median year of the dated buildings within
  60 m, else 120 m, else 250 m, capped at 2015, the year the footprints were traced; with no neighbour at all, 1950.
- A record dated only by a year appears at a fixed moment of that year, drawn per building, so the houses of one year
  do not all go up on the first of January.
- Stand-ins. The tax roll only describes buildings standing today. Where a 1970s tower replaced three 1900s houses, the
  roll leaves the lot empty in 1950. Without stand-ins, the West End of 1930 and 1950 has about 12 % of its ground
  built where the 1950 air photos show 50 to 90 % (measured). A lot gets a stand-in house when its building is younger
  than the year shown and either the period's air photo shows it built up (for a building at least 5 years younger than
  the photo), or its street was already old then: at least 6 buildings within 80 m, 60 % of them standing, today's
  building 25 years younger than their median. The stand-in takes the old neighbours' median year, height (14 m at most
  before 1930) and type, sits on the lot's footprint, and is replaced in the year today's building was built. It is
  never placed where it would cover more than 30 % of its footprint with a building that stands that year.
- A big stand-in becomes a row of houses, since one stand-in on a tower's whole footprint renders as a one-storey slab
  the size of the tower's base. A stand-in over 300 m² is cut across the long side of its footprint's smallest rectangle
  into 10 m lots (Vancouver's 33 ft lots; a block deeper than about 56 m gets back-to-back rows of 37 m lots). Each lot
  gets a gabled character house with 1.5 m side yards and front and back setbacks, at most 15 m deep and 10 m tall, with
  the stand-in's dates. A house that would lie less than 70 % on the old footprint is dropped. The ids are
  `<stand-in id>-s<k>`, so the same lot gives the same houses every year.
- Undated rail lines stand only today. OpenStreetMap has no opening year for them, and a SkyTrain line on a 1950 map is
  a worse error than a missing freight spur.
- Area overrides: a polygon where a period rule holds for a span of years. The place was still water (made land: its
  buildings, streets, trees and parks are left out and the polygon becomes water, except a building a sourced record
  says stood), today's trees or parks were not there yet, or streets stand only along standing buildings (a rail yard
  before the streets were laid). The qipu.org map uses one for north False Creek, rail yards before Expo 86; that outline
  was drawn by hand on the 1950 photos and is not in the rules file, but the mechanism is.

The built-up masks for the stand-in test are `model.Raster` grids in local metres, one per air-photo year, 0 for open
ground to 1 for built up (values between 0.4 and 0.6 are read as partly built). The rules file says which era years each
photo speaks for: Vancouver's 1950 photos for 1930 to 1954, the 1959 photos for 1955 to 1962. Ingest reads them from
the raw folder (`<name>_built.npz`: `share` as uint8, `x0`, `y0`, `cell`) and writes `ingest/evidence/<name>.npz`;
without them the stand-ins use the neighbour test alone.

The masks are made outside this repository, and the sample carries the ones the qipu.org map uses, cropped to
the West End (`examples/vancouver/west-end/napl1950_built.npz`, `napl1959_built.npz`; 4 m cells). Making them takes
more than a filter on the photo. The National Air Photo Library mosaics are greyscale and sit typically 5 to 12 m off the
City's footprints, by a different amount in each part of the city, so each photo is first aligned zone by zone against the
footprints. A classifier trained per photo on the footprints whose tax-roll year says they stood
then gives each 1 m pixel a probability of being built. The share of built pixels within about 40 m is then scaled so
that blocks the records call established read 0.6, water on the photo is cut out, and rail yards are capped. That is a
training pipeline with its own checks, not a few lines of code, so it is not part of this stage.

On the sample the 1950 photo makes the difference. With the masks, 182 lots get a stand-in in 1930
and 180 in 1950. After the big ones are cut into houses, that is 461 buildings in 1930 and 459 in 1950. Footprints cover
16 % of the land in 1930 and 18 % in 1950, against 30 % today: houses with yards cover less ground than the towers that
replaced them. With the neighbour test alone, 9 lots get a stand-in in 1930 and 11 in 1950, and footprints cover 9 % of
the land in 1950. The photo reads 91 % of the land as built up; that counts whole blocks with their yards, not roofs.

## The layer

A pixel of the past year is kept where it differs from today's painting: both images blurred by 2 px,
then a change of more than 26 in any channel, or one side painted and the other not. Everything else is transparent and
costs nothing to download. The kept area is feathered inward over about 2 px, so its edge does not show, and stays
exactly transparent outside.

Where the past year is water and today is water too, the layer is transparent and today's water shows. Two paintings
never give water the same blue, so the past year's water would show as flat boxes at the edges of its painted area. Old shores, where the past year is water and today is land, keep the past year.

A past year can be painted a zoom level or two coarser than today. Today's painting and class pass are then brought down
to the past year's size before the comparison, and the layer has the past year's size.

## The date maps

For a segment A to B, each pixel gets one date:

- a pixel showing a building that appears or goes in the segment, in A's or in B's render, takes that building's date
  (its year built, or its demolition, at its moment of the year), over all its walls and roof, whether or not the
  painting differs there. Buildings are read from the render's id pass: pixel value 1 + the building's index in its
  year's scene;
- a changed pixel within 12 px of such a building (its shadow, its lot) takes the nearest building's date;
- any other changed pixel gets a date from a smooth noise field: random values on a grid of 64 px cells, interpolated
  bilinearly, mapped into the middle 80 % of the segment. Blocks of one date would show during playback as rectangles
  switching tone; the smooth field has no edges;
- an unchanged pixel never switches.

A segment's date map has the size of its coarser year. The noise is seeded by the segment, so a re-run gives the same
bytes.

## Limits

- The tax roll knows only the buildings standing today. A building demolished before the City's permit records begin
  (2017) is in no record; stand-ins guess where such buildings stood and how tall they were, never what they looked like.
  Drawing them truly needs historical maps: Goad's 1912 fire-insurance atlas for Vancouver (the City holds it, but it
  could not be downloaded), the Sanborn atlases for San Francisco.
- A roll year is the parcel's, not the footprint's: a garage built later on an old lot appears with the house.
- Changes in the ground with no record (a lawn paved, a yard cleared) are spread over their segment, not known. Their
  date is a guess by design, and the dissolve makes that visible as a slow change rather than a false precise one.
- Structures that are gone and have no geometry today (the first Georgia viaduct, the old Granville and Cambie bridges,
  the streetcar lines) need traced outlines; the rules file can date only what today's data still holds.
- Opening years in the rules file are matched to today's streets by name; a bridge OpenStreetMap names differently is
  missed and stands in every year. Check the `streets left out` count in each scene's notes.

## Cost

All CPU, no network. The rules run in seconds for a district. The layers and date maps read every year's painted
canvas once and hold two years in memory at a time. A segment's date map for the West End canvas (2390 x 1720 px) takes
about a second, most of it the 12 px halo.
