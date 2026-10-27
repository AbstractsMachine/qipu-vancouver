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
