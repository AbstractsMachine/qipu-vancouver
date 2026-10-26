# Vancouver example

Nine pages of Vancouver City Council minutes from 1970 and 1974, enough to run the records pipeline offline, with the model's
answers recorded so no API key is needed.

```sh
make -C packages/records demo    # records: writes packages/records/build/demo/decisions.jsonl and decisions.geojson
make -C packages/records serve   # then open http://localhost:8000/map-preview/ to see them on a map
```

```sh
make -C packages/updates demo    # updates: the two meetings arrive a week apart; the second run processes only the new one
```

The map pipeline and viewer steps for the same sample are added here with those packages.

## The files

| file | what |
|---|---|
| `items.json` | the two archive.org items: the meetings of 9 June 1970 and 19 February 1974 |
| `pages.jsonl` | OCR text of pages 10–12 of the 1970 meeting and 0–5 of the 1974 meeting |
| `pagemaps.json` | each item's OCR page to viewer page map, from archive.org |
| `readings.jsonl` | the model's answers for those pages from the October 2026 run (Claude Haiku, prompt `v21-db2bcbe8fe`) |
| `gazetteer.csv` | the addresses, corners and neighbourhoods those pages need, from the city's open data |
| `updates/` | the updates config for this sample, `arrivals.json` (the made-up dates on which each meeting "appears", so a run can find a new one) and an empty `corrections.jsonl` |

## Where it comes from

The minutes were scanned by the [City of Vancouver Archives](https://searcharchives.vancouver.ca) and published on the
Internet Archive in the [council minutes collection](https://archive.org/details/cityofvancouvercouncilminutes) under
CC0 1.0: [19700609](https://archive.org/details/19700609) and [19740219](https://archive.org/details/19740219). The page text
is the text the model was sent: archive.org's OCR, joined line by line.

The pages are less than 100 years old, so the privacy rule applies to them. One records a claim by a private person; that name was withheld in
the page text and the answers with `qipu_records.verify.privacy.mask` before they were added here (see
[docs/privacy.md](../../docs/privacy.md)). Everything else is as read.

The gazetteer rows are taken from the City of Vancouver's
[property addresses](https://opendata.vancouver.ca/explore/dataset/property-addresses/),
[street intersections](https://opendata.vancouver.ca/explore/dataset/street-intersections/) and
[local area boundary](https://opendata.vancouver.ca/explore/dataset/local-area-boundary/) datasets. Contains information
licensed under the Open Government Licence – Vancouver. `qipu-records gazetteer` downloads the full set.
