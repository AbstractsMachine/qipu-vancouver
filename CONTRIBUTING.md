# Contributing

Bug reports, corrections to records and support for more cities are all welcome.

## Setting up

Each package is self-contained, with its own Makefile:

```sh
make -C packages/records install   # a virtual environment in packages/records/.venv with pinned tools
make -C packages/records check     # lint, types, tests with coverage, as CI runs them
make -C packages/records e2e       # the demo and its map page in a headless browser
```

`make check` at the root runs `check` in every package.

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
