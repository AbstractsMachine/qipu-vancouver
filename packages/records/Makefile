PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: install lock lint typecheck test e2e check demo serve clean

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
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

typecheck:
	$(BIN)/mypy

test:
	$(BIN)/pytest -m "not e2e" --cov --cov-report=term

e2e:
	$(BIN)/playwright install chromium
	$(BIN)/pytest -m e2e tests/e2e

check: lint typecheck test

demo:
	PYTHONPATH=src $(PYTHON) -m qipu_records.cli demo --sample ../../examples/vancouver --out build/demo

serve:
	@echo "open http://localhost:8000/map-preview/"
	$(PYTHON) -m http.server 8000 --bind 127.0.0.1

clean:
	rm -rf build .mypy_cache .ruff_cache .pytest_cache
