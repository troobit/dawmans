# Development tooling entry point. `make <target>` is the canonical way to build, test
# and lint; the targets wrap `uv run …` rather than replacing it.

.DEFAULT_GOAL := help
.PHONY: help build test lint spelling clean fetch-model bench

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Sync the virtual environment and install the package
	uv sync

test: ## Run the tests
	uv run pytest

lint: spelling ## Run linters (spelling, ruff)
	uv run ruff check .
	uv run ruff format --check .

spelling: ## Check spelling
	bash tools/check_spelling.sh

clean: ## Remove build artefacts
	rm -rf dist .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} +

fetch-model: ## Populate the gitignored models/ cache (one-off, needs network)
	uv run python tools/fetch_model.py

bench: ## Time a full-corpus rebuild (requirement 8.1); skipped when manuals/ is empty
	@if ! ls manuals/*.pdf >/dev/null 2>&1; then \
		echo "manuals/ holds no PDFs - skipping the 8.1 full-corpus benchmark."; \
		exit 0; \
	fi; \
	uv run pytest -m bench --no-header; status=$$?; \
	if [ $$status -eq 5 ]; then \
		echo "No benchmark is registered yet (requirement 8.1)."; \
		exit 0; \
	fi; \
	exit $$status
