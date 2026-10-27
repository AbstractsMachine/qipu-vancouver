.PHONY: install lint typecheck test e2e check demo build clean records-sample

install:
	npm ci

lint:
	npx eslint . --max-warnings 0
	npx prettier --check .

typecheck:
	npx tsc -p tsconfig.json

test:
	npx vitest run --coverage

e2e:
	npx playwright install --with-deps chromium
	npx playwright test

check: lint typecheck test

demo:
	npm run demo

build:
	npm run build
	npm run demo:build

clean:
	rm -rf dist demo-dist coverage playwright-report test-results

# The demo's ?decisions=sample: packages/records' own output on the Vancouver example, as the records demo writes it.
records-sample:
	$(MAKE) -C ../records demo
	cp ../records/build/demo/decisions.jsonl demo/public/sample/vancouver/decisions.jsonl
