PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: install lock lint typecheck test e2e e2e-live check demo serve build clean

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

install: $(BIN)/python
	$(BIN)/pip install --quiet --require-hashes -r requirements-dev.txt
	$(BIN)/pip install --quiet --no-build-isolation -e .

# Re-pin every development dependency, with hashes, after a change to requirements-dev.in.
lock: $(BIN)/python
	$(BIN)/pip install --quiet pip-tools
	$(BIN)/pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url \
	  --output-file requirements-dev.txt requirements-dev.in

lint:
	$(BIN)/ruff check src tests examples
	$(BIN)/ruff format --check src tests examples

typecheck:
	$(BIN)/mypy

test:
	$(BIN)/pytest -m "not e2e" --cov --cov-report=term

# The e2e test serves MapLibre from this copy instead of unpkg, so the browser needs no network. It is the npm tarball
# unpkg serves from, checked by hash, so the page's integrity attribute still holds.
MAPLIBRE_TGZ := build/vendor/maplibre-gl-4.7.1.tgz

$(MAPLIBRE_TGZ):
	mkdir -p $(@D)
	curl -fsSL --retry 3 -o $@.part https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-4.7.1.tgz
	echo "7e8a778cff03abad64ae19674977058616e1cf7c3712cabd1c35461ae465f923  $@.part" | shasum -a 256 -c -
	tar -xzf $@.part -C $(@D) package/dist/maplibre-gl.js package/dist/maplibre-gl.css
	mv $@.part $@

e2e: $(MAPLIBRE_TGZ)
	$(BIN)/playwright install chromium
	$(BIN)/pytest -m "e2e and not network" tests/e2e

# The archive.org page links of the demo, requested for real. Not part of CI, which runs without the network.
e2e-live:
	$(BIN)/pytest -m network tests/e2e

check: lint typecheck test

demo:
	PYTHONPATH=src $(PYTHON) -m qipu_records.cli demo --sample ../../examples/vancouver --out build/demo

serve:
	@echo "open http://localhost:8000/map-preview/"
	$(PYTHON) -m http.server 8000 --bind 127.0.0.1

# A wheel in dist/, checked to carry the prompts the reader loads at run time.
build:
	rm -rf dist
	$(BIN)/python -m pip wheel --quiet --disable-pip-version-check --no-deps --no-build-isolation --wheel-dir dist .
	$(BIN)/python -m zipfile -l dist/*.whl | grep -q "read/prompts/vancouver.txt"

clean:
	rm -rf build dist .mypy_cache .ruff_cache .pytest_cache
