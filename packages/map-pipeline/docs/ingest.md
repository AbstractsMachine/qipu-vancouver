# Ingest

The first stage. It gathers the open data that describes an area of a city today and writes it in one shape the scene
stage can read: GeoJSON layers in degrees, two height grids in local metres, and a list of sources with their licences.

```
qipu-map ingest --city vancouver --area west-end            # fetch what is missing, then normalise
qipu-map ingest --area west-end --raw ../../examples/vancouver/west-end   # no network: use this raw folder as it is
```

`--margin` (default 60 m) is how far past the area's box the stage fetches. The scene and the camera see a little past
the box, and a building that straddles the edge should come whole.

## Two halves

**Fetch** talks to the network and nothing else. Each source's answer is written as it came to
`<work>/<city>/<area>/ingest/raw/`, one file per source. A file that is already there is the cache: it is not fetched
again, so a run that failed halfway picks up where it stopped, and deleting one file refetches just that source. The
date each source was fetched goes to `raw/retrieved.json`.

**Normalise** reads the raw folder and writes the layers. It is pure apart from that reading and writing, and the same
raw folder always gives the same bytes. With `--raw` the fetch half is skipped, which is how CI and `make sample` run.
The stage also writes a `.stamp`: when the raw files and settings have not changed, a second run does nothing.

## Sources

Defined in `src/qipu_map/ingest/sources.py` (Vancouver's defaults); a city file can override any field with a
`[sources.<id>]` table.

| id | Dataset | Raw file | Licence |
|---|---|---|---|
| `footprints` | City of Vancouver, Building Footprints 2015 | `footprints.geojson` | OGL-Vancouver |
| `parcels` | City of Vancouver, Property parcel polygons | `parcels.geojson` | OGL-Vancouver |
| `tax_roll` | City of Vancouver, Property tax report (report year 2026) | `tax_roll.json` | OGL-Vancouver |
| `trees` | City of Vancouver, Public trees | `trees.geojson` | OGL-Vancouver |
| `parks` | City of Vancouver, Parks polygons | `parks.geojson` | OGL-Vancouver |
| `streets`, `lanes` | City of Vancouver, Public streets and Lanes | `streets.geojson`, `lanes.geojson` | OGL-Vancouver |
| `row_widths` | City of Vancouver, Right-of-way widths | `row_widths.geojson` | OGL-Vancouver |
| `shoreline` | City of Vancouver, Shoreline 2002 (cut to the box) | `shoreline.geojson` | OGL-Vancouver |
| `osm` | OpenStreetMap through Overpass: buildings, highways, rail, water, coastline | `osm.json` | ODbL |
| `lidar` | LidarBC 2025, 1 m DSM and DEM tiles | `lidar_tiles.json`, `lidar_dsm.npz`, `lidar_dem.npz` | OGL-BC |

The City's portal is an Opendatasoft one: the stage asks its export API for records whose geometry intersects the box,
with only the fields it reads. The tax roll has no geometry, so it is asked for the land coordinates of the parcels in
the box, 150 at a time. Overpass gets one query for everything, tried on three public mirrors in turn.

LiDAR: the province's tile index (an ArcGIS FeatureServer) lists the 2025 tiles that touch the box. Each tile is opened
over HTTP and only the window over the area is read; GDAL fetches the byte ranges it needs. The window is sampled at the
centre of every cell of a 1 m grid in local metres, nearest cell (so a building edge stays a step), and stored as int16 decimetres
(half the size of float32, 10 cm steps, well inside the survey's own accuracy). This half needs the `lidar` extra
(rasterio and pyproj); normalising does not.

## Outputs

In `<work>/<city>/<area>/ingest/`. Every GeoJSON layer is a FeatureCollection sorted by id, coordinates rounded to 7
decimals; the id is also in `properties.id`.

- `buildings.geojson`: Polygon; `year_built`, `year_source` (`tax_roll`, `osm`, `convention` or null),
  `year_improved` (see below; null for most), `height_m` and
  `levels` (from OSM, when it has them), `use` (the parcel's zoning district for survey footprints, the OSM building
  tag for the others), `source` (`footprints` or `osm`). Ids are `van15-<object_id>` and `osm-w<id>` / `osm-r<id>`.
- `streets.geojson`: LineString; `kind` (`arterial`, `residential`, `lane`, `path`, `rail`), `width_m`, `name`.
- `trees.geojson`: Point; `genus`, `species`, `height_m`, `diameter_cm`, `year_planted`.
- `parks.geojson`: Polygon, cut to the fetch box; `name`.
- `water.geojson`: Polygon, cut to the fetch box; `kind` (`sea`, `lake`, `river`, `pond`).
- `dsm.npz`, `dem.npz`: `model.Raster` grids, 1 m cells, covering the area plus the margin.
- `sources.json`: one entry per source with `name`, `url`, `licence`, `attribution`, `retrieved` and `features`
  (the records it gave: features, rows, OSM elements, or LiDAR cells with a value).

## Rules and why

**Year built.** A 2015 footprint takes the year of the parcel its centroid stands on, from the tax roll. No nearest
parcel is tried when it stands on none: a pier or a building on a road allowance stays undated instead of borrowing a
neighbour's year. Where parcels are stacked (air-space parcels over one lot), the dated one with the most roll rows
wins; the first by number is often an undated shell, and six towers over 30 m in the sample were undated that way.

A parcel's year is the most common year among its roll rows, ties going to the oldest. A strata tower has one row
per unit, all with the tower's year, and now and then one row still carrying the old lot's year. Taking the oldest row
would stand the Mirabel (2021, 150 rows, one of them 1951) and a 2014 tower (one row of 1949) in a 1950s render. The roll's placeholder year 1800 means unknown. The roll only describes buildings standing today, so a garage
takes its house's year.

**Improvement year.** When most of a parcel's rows give a big-improvement year later than the year built, it goes out
as `year_improved`. That is how the roll tells a heritage front with a tower added behind it: Tudor Manor on Beach
Avenue is one footprint, built 1928, with a 60 m tower from 1989. `year_built` stays 1928, which is right for the
front; the eras stage should not stand the tall part before `year_improved`.

**Buildings the survey does not have.** The City has not updated its footprints since 2015. An OSM building with less
than 30 % of its area on survey footprints is added. Overlap is the only link between the two datasets, and 30 % lets
an outline that is shifted a metre or two still count as the same building. An OSM building at least 60 % inside a
footprint and the footprint at least 60 % inside it is the same building: the footprint stays, and takes OSM's height
and storeys. Roofs, carports, construction sites, ruins, underground and floating things, and anything under 20 m²
are left out.

**Dating them.** An OSM date tag (`start_date` and its cousins) first. Then the parcel's roll year when it can only be
this building's: a year after the survey, or any year when the survey traced nothing on that parcel. Then the
convention: `footprint_survey_year` (2016), flagged `convention`, so a past-year render never shows a building it cannot
date. In the sample the middle rule dates twelve buildings the 2015 survey missed (a block around
Burnaby and Harwood with 1950s and 1960s apartment towers such as Pat Rose Place, 1969) that the convention would have
called new.

**OSM heights.** A `height` tag is used unless the building's own storey count makes it impossible (over 7 m a storey:
a proposal or a typo). Storeys alone become a height at 3.4 m a storey for homes, 4.2 m for offices and shops and 3.8 m
otherwise.

**Streets.** The map draws streets by the City's street-use classes: Arterial, Secondary Arterial and Collector
become `arterial`, Residential `residential`, the City's lanes `lane`, and its few closed, leased or recreational
streets `path`. The name is the hundred-block label minus its range. OSM adds only what the City does not publish as
streets: footpaths, cycle paths, steps and pedestrian streets (not sidewalks or crossings, which belong to their street)
and rail that is not in a tunnel.

**Water.** The map draws the City's 2002 shoreline, but a bare line does not say which side is sea.
OSM's coastline does (land on the left of the way). The box is cut along the City's line and each piece is called sea
or land by the side of the nearest OSM coastline segment. Where the City has no shoreline in the box, the OSM coastline
cuts too. Lakes, ponds and rivers come from OSM.

**Heights.** DSM minus DEM of the same survey, never mixed across surveys: their vertical datums differ.

## What it leaves out, and limits

- The qipu.org map dates the newest buildings with the City's building permits (issue year plus a measured lag per
  class) and drops 2015 footprints the 2025 LiDAR reads as gone. Neither is here yet; a demolished-since-2015 building
  is still in `buildings.geojson`.
- The qipu.org map moves each OSM outline by the local median offset between OSM and the survey (about 1.2 m) before
  adding it, and adds OSM towers over low survey records that they replaced. Both are left out: they matter at city
  scale and are not needed for an area the size of the sample.
- Right-of-way widths are property line to property line, not kerb to kerb, and published in feet (converted here). Here a street takes the nearest label within 20 m, and 17 of the sample's 135 City street
  and lane lines get none.
- A footprint the City traced around a whole complex keeps one year. St. Paul's Hospital is one 19,900 m² outline on
  one roll row, 1912, with 40 m wings on it; nothing in the roll dates the wings.
- 8 footprints in the sample stay undated, among them two 50 m towers on a parcel the roll has carried with no year
  since it was created in 2023. The eras stage gives undated buildings a year from their neighbours.
- The tree dataset stopped publishing planting dates in 2025, so `year_planted` is null for Vancouver.
- An area entirely at sea, with no coastline crossing it, gets no sea polygon.
- Heights come from LidarBC 2025, as on the painted qipu.org map. The 2015 footprints and the 2025 LiDAR are ten years apart: a building that changed in between gets the
  height of what stands there now.
- No bathymetry (CHS NONNA-10) and no canopy layer: the scene stage derives canopy from the DSM.

## Cost and time

The West End sample (800 × 600 m plus margin) fetches in about a minute and 2.5 MB. The whole city is about 1.3 GB of
LiDAR windows and 300 MB of vector data; Overpass may refuse a whole-city query at busy times, so split big areas.
Normalising the sample takes a fraction of a second.
