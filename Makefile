# Development tooling entry point. `make <target>` is the canonical way to
# build/test/lint.

.DEFAULT_GOAL := help
.PHONY: help build test lint spelling clean new-project

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Sync the dev environment (uv; serve extra, never ingest)
	uv sync --extra serve

test: ## Run the tests
	uv run pytest

lint: spelling ## Run linters
	uv run ruff check src tests

spelling: ## Check spelling
	bash tools/check_spelling.sh

clean: ## Remove build artefacts
	rm -rf dist .pytest_cache .ruff_cache

