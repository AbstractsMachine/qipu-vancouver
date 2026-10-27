# Map sample: Vancouver, West End

The raw open data for the `west-end` area of the map pipeline's `cities/vancouver.toml`: from 1139 Pendrell Street (the
park site council bought in 1974, also in the records sample) west and south to the Sunset Beach shore of English Bay.
The box is 49.2782, -123.1405 to 49.2836, -123.1295 (about 800 × 600 m); every file covers it plus 60 m on each side.

These are the files `qipu-map ingest` fetches, kept as they came, so the whole pipeline can run offline:

```
qipu-map ingest --city vancouver --area west-end --raw ../../examples/vancouver/west-end   # from packages/map-pipeline
```

All of it was retrieved on 26 October 2026 (`retrieved.json`). About 2.5 MB.

## Files

| File | What it is | Records | Source |
|---|---|---|---|
| `footprints.geojson` | Building outlines traced in 2015 (`object_id`) | 362 | City of Vancouver, [Building Footprints 2015](https://opendata.vancouver.ca/explore/dataset/building-footprints-2015/) |
| `parcels.geojson` | Property parcels (`tax_coord`) | 462 | City of Vancouver, [Property parcel polygons](https://opendata.vancouver.ca/explore/dataset/property-parcel-polygons/) |
| `tax_roll.json` | The 2026 roll's rows for those parcels: `land_coordinate`, `year_built`, `big_improvement_year`, `zoning_district` | 3,416 | City of Vancouver, [Property tax report](https://opendata.vancouver.ca/explore/dataset/property-tax-report/) |
| `trees.geojson` | Boulevard and park trees: genus, species, height, trunk diameter | 1,022 | City of Vancouver, [Public trees](https://opendata.vancouver.ca/explore/dataset/public-trees/) |
| `parks.geojson` | Park polygons and names | 6 | City of Vancouver, [Parks - polygon representation](https://opendata.vancouver.ca/explore/dataset/parks-polygon-representation/) |
| `streets.geojson` | Street centrelines, hundred-block label, street use | 102 | City of Vancouver, [Public streets](https://opendata.vancouver.ca/explore/dataset/public-streets/) |
| `lanes.geojson` | Lane centrelines | 33 | City of Vancouver, [Lanes](https://opendata.vancouver.ca/explore/dataset/lanes/) |
| `row_widths.geojson` | Right-of-way width labels (points, in feet) | 84 | City of Vancouver, [Right-of-way widths](https://opendata.vancouver.ca/explore/dataset/right-of-way-widths/) |
| `shoreline.geojson` | The 2002 shoreline, cut to the box | 1 | City of Vancouver, [Shoreline 2002](https://opendata.vancouver.ca/explore/dataset/shoreline-2002/) |
| `osm.json` | Buildings, highways, rail, water and coastline, Overpass JSON with tags and geometry | 1,019 elements | [OpenStreetMap](https://www.openstreetmap.org) via the Overpass API |
| `lidar_tiles.json` | The LiDAR tiles the grids were read from (one DSM, one DEM, map tile 092g025_3_4_1, flown 26 August 2025) | 2 | [LidarBC](https://www2.gov.bc.ca/gov/content/data/geographic-data-services/lidarbc) tile index |
| `lidar_dsm.npz` | Surface model (roofs, trees) on the local 1 m grid: `dm` int16 decimetres (−32768 = no data), `x0`, `y0` north-west corner in local metres, `cell` | 920 × 722 cells | LidarBC 2025 1 m DSM |
| `lidar_dem.npz` | Bare-earth model, same grid | 920 × 722 cells | LidarBC 2025 1 m DEM |
| `napl1950_built.npz`, `napl1959_built.npz` | How built up the 1950 and 1959 air photos show each 4 m cell: `share` uint8 (255 = fully built, 153 = an established block), `x0`, `y0` north-west corner in local metres, `cell`. Read by the eras stage's stand-ins | 231 × 182 cells | Cropped on 26 October 2026 from the live map's masks (made 21 October 2026) of the [NAPL Salish mosaics](https://open.canada.ca/data/en/dataset/f498bb69-3982-4b62-94db-4c0e0065bc17), Natural Resources Canada |
| `retrieved.json` | The date each source was fetched | | |

The City files keep only the fields the ingest reads (the API's `select`). The LiDAR grids were read from the
province's GeoTIFF tiles over HTTP, window by window, and sampled at the nearest cell onto the map's local metre grid,
so no projection library is needed to run the sample.

## Licences and attribution

- City of Vancouver data: Open Government Licence – Vancouver. "Contains information licensed under the Open Government
  Licence – Vancouver."
- LidarBC: Open Government Licence – British Columbia. "Contains information licensed under the Open Government
  Licence – British Columbia."
- National Air Photo Library mosaics (Natural Resources Canada): Open Government Licence – Canada 2.0. "Contains
  information licensed under the Open Government Licence – Canada." The masks are derived from the photos; how they are
  made is described in `docs/eras.md`.
- OpenStreetMap: Open Database Licence 1.0. "© OpenStreetMap contributors." `osm.json` is a database extract and stays
  under the ODbL; images rendered from it are not.
