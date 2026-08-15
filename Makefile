# Development tooling entry point. `make <target>` is the canonical way to build, test
# and lint; the targets wrap `uv run …` and `pnpm …` rather than replacing them.

.DEFAULT_GOAL := help
.PHONY: help build build-py build-serve test test-py lint lint-py format spelling clean \
	fetch-model sections fixtures bench bench-ingest bench-answer bench-retrieval serve \
	web-install web-build web-test web-e2e web-lint dev dev-web dev-engine

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: build-py web-build ## Build both halves: the Python environment and the browser surface

build-py: ## Sync the dev environment (both extras) and install the package
	uv sync --all-extras

build-serve: ## Sync what the API host runs — serve only, never ingest (AGPL, Decision 6)
	uv sync --extra serve

test: test-py web-test ## Run every suite

test-py: ## Run the Python tests
	uv run pytest

lint: spelling lint-py web-lint ## Run every linter

lint-py: ## Run ruff over the Python tree
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply ruff's formatting
	uv run ruff format .

spelling: ## Check spelling
	bash tools/check_spelling.sh

serve: ## Run the answer engine on loopback, serving web/build at / when it exists
	uv run dawmans serve

clean: ## Remove build artefacts
	rm -rf dist .pytest_cache .ruff_cache web/build web/.svelte-kit
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} +

fetch-model: ## Populate the gitignored models/ cache (one-off, needs network)
	uv run python tools/fetch_model.py

sections: ## Find real manual sections for a triage fix: pointer — make sections ARGS="direct monitor"
	@uv run python tools/sections.py $(ARGS)

fixtures: ## Recapture tests/fixtures/ from manuals/; needs the vendor PDFs locally
	@if ! ls manuals/*.pdf >/dev/null 2>&1; then \
		echo "manuals/ holds no PDFs - see specs/data/manual-corpus/prerequisites.md."; \
		echo "Writing the synthetic rejection fixtures only."; \
		uv run python tools/capture_fixture.py --rejections; \
	else \
		uv run python tools/capture_fixture.py --all; \
	fi

bench: bench-ingest bench-answer ## Run both timing suites

bench-ingest: ## Time a full-corpus rebuild (manual-corpus 8.1); skipped when manuals/ is empty
	@if ! ls manuals/*.pdf >/dev/null 2>&1; then \
		echo "manuals/ holds no PDFs - skipping the 8.1 full-corpus benchmark."; \
		exit 0; \
	fi; \
	uv run pytest -m bench --no-header; status=$$?; \
	if [ $$status -eq 5 ]; then \
		echo "No benchmark is registered yet (manual-corpus 8.1)."; \
		exit 0; \
	fi; \
	exit $$status

bench-answer: ## Real-provider, real-index answer timing (skips when either is absent)
	uv run python tools/bench.py

bench-retrieval: ## Real-index retrieval timing (4.2) alone — needs no provider key
	uv run python tools/bench.py --retrieval-only

web-install: ## Install web/ dependencies
	cd web && pnpm install

web-build: web-install ## Build the browser surface to web/build
	cd web && pnpm build

web-test: web-install ## Run the web unit and component tests
	cd web && pnpm test

web-e2e: web-install ## Run the Playwright browser and accessibility suite
	cd web && pnpm test:e2e

web-lint: web-install ## Type-check the browser surface (svelte-check)
	cd web && pnpm check

dev: ## Run the web dev server and the answer engine together
	$(MAKE) -j2 dev-web dev-engine

dev-web:
	cd web && pnpm dev

dev-engine:
	uv run dawmans serve
