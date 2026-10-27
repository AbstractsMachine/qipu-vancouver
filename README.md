# qipu-vancouver

[![ci](https://github.com/AbstractsMachine/qipu-vancouver/actions/workflows/ci.yml/badge.svg)](https://github.com/AbstractsMachine/qipu-vancouver/actions/workflows/ci.yml)

City councils have kept minutes for more than a century, and many of them have been scanned and put on the Internet Archive.
They answer questions people still ask: who approved this building, when was this street widened, how did the vote go. But a
scan is hard to search, and its OCR text is harder still.

This repository turns those scans into facts anyone can check, and shows them on a painted map of the city, year by year.
It was built for the Internet Archive and Futureproof Festival Fellowship.

```
scanned minutes on archive.org ──▶ decision records ──▶ records kept current ──┐
                                   packages/records     packages/updates       ├──▶ map viewer
open city data ──────────────────▶ painted map tiles, one set per year ────────┘    packages/viewer
                                   packages/map-pipeline
```

**Live demo:** https://www.qipu.org/vancouver, Vancouver City Council decisions from the 1960s to the 1980s on the map.

| package | what it does | language |
|---|---|---|
| [`packages/records`](packages/records) | reads each scanned page with a language model, then checks every decision in plain code: the quote must be on the page, the date comes from the minutes, private names in sensitive matters are withheld, and each record links to its page in the archive.org viewer | Python 3.11+, standard library only |
| [`packages/updates`](packages/updates) | keeps the records current on a schedule: finds new and re-scanned minutes, extracts only those, checks the release against the pages, publishes it as a new version, rolls back in one command, and opens an issue when a run fails | Python 3.11+, depends on records |
| [`packages/map-pipeline`](packages/map-pipeline) | turns open city data into the painted map that plays through time: a 3D scene of the city, a Blender render, an AI paint pass, the past years and the tiles | Python 3.12+ (numpy, Pillow, shapely); Blender and FLUX.2 klein on a GPU |
| [`packages/viewer`](packages/viewer) | the web map: painted tiles, a year slider, and the records of each place | TypeScript, React, Leaflet |

## Quickstart

Every package runs on the bundled Vancouver sample with no API key and no GPU. You need `make`, Python 3.12 and Node 20
or newer.

```sh
git clone https://github.com/AbstractsMachine/qipu-vancouver && cd qipu-vancouver

make -C packages/records demo                 # read 9 pages with recorded model answers, check them: build/demo/
make -C packages/updates install demo         # two scheduled runs a week apart; the second processes only the new meeting
make -C packages/map-pipeline install sample  # every map stage on a CPU, about two minutes: build/sample/release/
make -C packages/viewer install demo          # the web map at http://localhost:5173 (Ctrl-C to stop)
```

To run every package's lint, type checks and tests with coverage, as CI does:

```sh
make install check
```

[`examples/vancouver`](examples/vancouver) explains the sample, and each package's README says how to run it on more data.

## Documentation

- [docs/architecture.md](docs/architecture.md): how the packages fit together, and what passes between them (one page)
- [docs/data-model.md](docs/data-model.md): every field of a decision record
- [docs/tiles-format.md](docs/tiles-format.md): the tile pyramid and manifest the map pipeline writes and the viewer reads
- [docs/accuracy.md](docs/accuracy.md): how often the records are wrong, how that was measured, and what the numbers do not say
- [docs/privacy.md](docs/privacy.md): which names are withheld, and why
- [docs/updates.md](docs/updates.md): the scheduled refresh: how it runs, how to add a source, pause it or roll back

## Contributing

Each package has its own Makefile with the same targets (`install`, `check`, `test`, `e2e`, `demo`, `build`), and the root
Makefile runs a target in every package. CI runs each package's jobs when that package changes, the pre-commit hooks, and a
secret scan of the full history on every push; the one required check is `ci-ok`. [CONTRIBUTING.md](CONTRIBUTING.md) has
the setup, the conventions and how to report a wrong record.

## Licences

Code is under the [Apache License 2.0](LICENSE). Data the code produces, and the sample data in `examples/`, are dedicated to the
public domain under [CC0 1.0](LICENSE-DATA), except the third-party open data that [LICENSE-DATA](LICENSE-DATA) lists with its
own terms (City of Vancouver, LidarBC, Natural Resources Canada, OpenStreetMap). [NOTICE](NOTICE) carries their attribution
lines.

## Credits

The scans and their OCR are the work of the [Internet Archive](https://archive.org) and the archives and libraries that
digitised the records: the [City of Vancouver Archives](https://searcharchives.vancouver.ca), whose 1970s minutes were digitised
with funding from the British Columbia History Digitization Program at the University of British Columbia, and the
[San Francisco Public Library](https://sfpl.org). Addresses and neighbourhoods come from the
[City of Vancouver Open Data Portal](https://opendata.vancouver.ca). Maps use [MapLibre GL JS](https://maplibre.org) and
[OpenStreetMap](https://www.openstreetmap.org/copyright) data.
