PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
SAMPLE_WORK ?= build/sample

.PHONY: install lock lint typecheck test check e2e demo sample sample-gpu build clean

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

install: $(BIN)/python
	$(BIN)/pip install --quiet --require-hashes -r requirements-dev.txt
	$(BIN)/pip install --quiet --no-build-isolation --no-deps -e .

# Re-pin every development dependency, with hashes, after a change to requirements-dev.in.
lock: $(BIN)/python
	$(BIN)/pip install --quiet pip-tools
	$(BIN)/pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url \
	  --output-file requirements-dev.txt requirements-dev.in

lint:
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

typecheck:
	$(BIN)/mypy

test:
	$(BIN)/pytest -m "not network and not gpu and not e2e" --cov --cov-report=term

e2e:
	$(BIN)/pytest -m e2e tests/e2e

check: lint typecheck test

# The whole chain on the bundled sample, on a CPU: the preview renderer and the identity painter stand in for Blender and
# the AI model, so it runs anywhere in about two minutes.
sample:
	$(BIN)/qipu-map sample --work $(SAMPLE_WORK)

demo: sample

# The same chain with Blender and FLUX.2 klein. Needs Blender 4.2+ on PATH (or BLENDER=...) and a CUDA GPU with 24 GB;
# see docs/render.md and docs/paint.md.
sample-gpu:
	$(BIN)/qipu-map sample --work $(SAMPLE_WORK)-gpu --render-backend blender --paint-backend diffusers

# A wheel in dist/, checked to carry the city file and the paint prompts the stages load at run time.
build:
	rm -rf dist
	$(BIN)/python -m pip wheel --quiet --disable-pip-version-check --no-deps --no-build-isolation --wheel-dir dist .
	$(BIN)/python -m zipfile -l dist/*.whl | grep -q "qipu_map/cities/vancouver.toml"
	$(BIN)/python -m zipfile -l dist/*.whl | grep -q "qipu_map/paint/prompts/"

clean:
	rm -rf build dist .mypy_cache .ruff_cache .pytest_cache .coverage
