.PHONY: install lint typecheck test e2e check demo build clean

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
