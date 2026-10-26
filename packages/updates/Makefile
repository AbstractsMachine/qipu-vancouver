PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
EXAMPLE := ../../examples/vancouver/updates/updates.toml
DEMO := build/demo

.PHONY: install lock lint typecheck test e2e check demo clean

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

# qipu-records comes from this repository, not from an index.
install: $(BIN)/python
	$(BIN)/pip install --quiet --require-hashes -r requirements-dev.txt
	$(BIN)/pip install --quiet --no-build-isolation -e ../records
	$(BIN)/pip install --quiet --no-build-isolation -e .

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
	$(BIN)/pytest -m "not e2e" --cov --cov-report=term

e2e:
	$(BIN)/pytest -m e2e tests/e2e

check: lint typecheck test

# Two scheduled runs a week apart on the Vancouver sample: the second finds one new meeting and processes only that one.
demo:
	rm -rf $(DEMO)
	$(BIN)/qipu-updates run --config $(EXAMPLE) --store $(DEMO)/store --work $(DEMO)/work --as-of 2026-10-19 --run-id demo-1
	$(BIN)/qipu-updates run --config $(EXAMPLE) --store $(DEMO)/store --work $(DEMO)/work --as-of 2026-10-26 --run-id demo-2
	$(BIN)/qipu-updates releases --config $(EXAMPLE) --store $(DEMO)/store

clean:
	rm -rf build .mypy_cache .ruff_cache .pytest_cache .coverage
