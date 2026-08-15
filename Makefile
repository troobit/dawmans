# Development tooling entry point. `make <target>` is the canonical way to build, test
# and lint; the targets wrap `uv run …` rather than replacing it.

.DEFAULT_GOAL := help
.PHONY: help build build-serve test lint spelling clean fetch-model fixtures \
	bench bench-ingest bench-answer serve

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Sync the dev environment (both extras) and install the package
	uv sync --all-extras

build-serve: ## Sync what the API host runs — serve only, never ingest (AGPL, Decision 6)
	uv sync --extra serve

test: ## Run the tests
	uv run pytest

lint: spelling ## Run linters (spelling, ruff)
	uv run ruff check .
	uv run ruff format --check .

spelling: ## Check spelling
	bash tools/check_spelling.sh

serve: ## Run the answer engine on loopback
	uv run dawmans serve

clean: ## Remove build artefacts
	rm -rf dist .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} +

fetch-model: ## Populate the gitignored models/ cache (one-off, needs network)
	uv run python tools/fetch_model.py

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
