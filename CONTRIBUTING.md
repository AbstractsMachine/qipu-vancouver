# Contributing

Bug reports, corrections to records and support for more cities are all welcome.

## Setting up

Each package is self-contained, with its own Makefile and the same targets:

```sh
make -C packages/records install   # a virtual environment in packages/records/.venv with pinned, hashed tools
make -C packages/records check     # lint, types, tests with coverage, as CI runs them
make -C packages/records e2e       # the end-to-end test on the sample (here: the demo and its map page in a browser)
```

`make install check` at the root does the same in every package. The Python packages pin their development tools with
hashes in `requirements-dev.txt` (`make lock` re-pins after a change to `requirements-dev.in`); the viewer pins with
`package-lock.json`.

Then install the commit hooks, which run ruff, the type checks, eslint and prettier, and a secret scan on the files you
change:

```sh
pip install pre-commit && pre-commit install
pre-commit run --all-files         # the same hooks over everything, as CI runs them
```

## Layout

```
packages/<name>/   one package: its README, ARCHITECTURE.md where it has one, Makefile, src/, tests/
docs/              what crosses package boundaries: the record and tile formats, accuracy, privacy, updates
examples/          the shared sample every package's demo and end-to-end test runs on
```

The Python packages keep their tests in three layers: `tests/unit` (one module at a time), `tests/integration` (several
modules together, on the sample) and `tests/e2e` (the package's demo end to end). The viewer keeps its unit and component
tests beside the code (`src/**/*.test.ts(x)`) and its browser tests in `e2e/`. None of them uses the network: every Python test
suite fails a test that tries to, and the viewer's browser tests serve every remote request from fixtures.

## Where does X live

| to change or find | code | tests | docs |
|---|---|---|---|
| the meeting date of a decision (the `date` field, and `date_source`) | `packages/records/src/qipu_records/verify/dates.py` | `packages/records/tests/unit/verify/test_dates.py`, the real pages in `test_dates_real_pages.py`, and `tests/integration/test_pipeline.py` (`test_dates_come_from_the_meeting_headers`) | [docs/data-model.md](docs/data-model.md) |
| which names are withheld | `packages/records/src/qipu_records/verify/privacy.py` and `privacy_patterns.toml` | `packages/records/tests/unit/verify/test_privacy.py`; the update gate is `packages/updates/src/qipu_updates/gates/privacy.py` | [docs/privacy.md](docs/privacy.md) |
| the quote must be on the page | `packages/records/src/qipu_records/verify/quotes.py` | `tests/unit/verify/test_quotes.py` | [docs/accuracy.md](docs/accuracy.md) |
| fetching from archive.org (metadata, OCR text, page links) | `packages/records/src/qipu_records/fetch/archive.py` | `packages/records/tests/unit/fetch/test_archive.py`, on the recorded files in `tests/fixtures/archive/` | [packages/records/README.md](packages/records/README.md) |
| the model's reading of a page | `packages/records/src/qipu_records/read/` | `packages/records/tests/unit/read/` | [packages/records/ARCHITECTURE.md](packages/records/ARCHITECTURE.md) |
| building the map tiles | `packages/map-pipeline/src/qipu_map/tiles/` (pyramids), `eras/` (date maps), `publish/` (the release) | `packages/map-pipeline/tests/unit/tiles/`, `tests/integration/test_chain.py` | [docs/tiles-format.md](docs/tiles-format.md), `packages/map-pipeline/docs/tiles.md` |
| the viewer's panels (record panel, decision list, year slider) | `packages/viewer/src/panels/` | beside each file: `RecordPanel.test.tsx`, and `packages/viewer/e2e/` | [packages/viewer/README.md](packages/viewer/README.md) |
| the update gates that stop a bad release | `packages/updates/src/qipu_updates/gates/` (`suite.py` runs them) | `packages/updates/tests/unit/test_gates.py` | [docs/updates.md](docs/updates.md) ("Gates") |
| releasing and rolling back | `packages/updates/src/qipu_updates/release/` and `publish/` (`qipu-updates rollback`) | `tests/unit/test_publish.py`, `tests/integration/test_loop.py` | [docs/updates.md](docs/updates.md) ("A release", "Rolling back") |

## Running one package's tests

From the package directory, or with `make -C packages/<name>`:

```sh
cd packages/records
make install                                     # once: the virtual environment in .venv
.venv/bin/pytest tests/unit/verify/test_dates.py # one file
.venv/bin/pytest -k running_head                 # tests whose name matches
make test                                        # all unit and integration tests, with coverage
```

The viewer's equivalent is `cd packages/viewer && npx vitest run src/panels/RecordPanel.test.tsx`.

## Adding a regression fixture

A fixture is a few lines of a real page, not the whole page. For the records package:

1. Find the page on archive.org and note the item identifier and the scan page (counting from 0, as `fetch_page_texts`
   returns pages). `make -C packages/records demo` shows how an item's text is fetched.
2. Copy only the lines the rule needs, with the OCR's spacing and mistakes, into `packages/records/tests/fixtures/real_pages.py`
   as a constant. Put the item and page in the comment above it: `# https://archive.org/details/<item>, scan page <n>: why`.
3. Add a test that uses the constant in the matching `tests/unit/` file (`test_dates_real_pages.py` is the model), and check that
   it fails without your fix.
4. Run `make -C packages/records check`.

Keep fixtures small and make sure they pass the privacy rule in [docs/privacy.md](docs/privacy.md).

## Reporting a wrong record

Open an issue with the record's `id` and `page_url`, and say what the page actually shows. If the mistake is in the OCR text
itself, say so: that is archive.org's text, and we can only work around it.

## Changing the code

- Keep each package's runtime dependencies to what it truly needs. The records core uses only the Python standard library;
  a new model client goes in as an optional extra, imported inside its reader.
- Every rule that changes a published record needs a test that shows the case it fixes, ideally taken from a real page.
- The formats in [docs/data-model.md](docs/data-model.md) and [docs/tiles-format.md](docs/tiles-format.md) are contracts between
  packages. Change them in the same pull request as every package that reads them.
- Sample data must be openly licensed and must pass the privacy rule in [docs/privacy.md](docs/privacy.md).

## Pull requests

Keep them small and say why the change is needed. The `ci-ok` check must pass. By contributing you agree that your code is
licensed under the Apache License 2.0 and any data under CC0 1.0.
