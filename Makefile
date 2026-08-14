# Development tooling entry point. When a Makefile exists, `make <target>` is the
# canonical way to build/test/lint — fill in the TODO targets once the stack is chosen.

.DEFAULT_GOAL := help
.PHONY: help build test lint spelling clean new-project \
	web-install web-build web-test dev dev-web dev-engine

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: web-build ## Build the project

test: web-test ## Run the tests

web-install: ## Install web/ dependencies
	cd web && pnpm install

web-build: web-install ## Build the browser surface to web/build
	cd web && pnpm build

web-test: web-install ## Run the web unit and component tests
	cd web && pnpm test

dev: ## Run the web dev server and the answer engine together
	$(MAKE) -j2 dev-web dev-engine

dev-web:
	cd web && pnpm dev

dev-engine:
	@echo "answer engine not implemented yet (specs/api/answer-engine);"
	@echo "the dev proxy for /turn, /passages, /sources, /provider has nothing to reach until it runs"

lint: spelling ## Run linters (spelling today; add stack linters when chosen)

spelling: ## Check spelling
	bash tools/check_spelling.sh

clean: ## Remove build artefacts (TODO: configure for the chosen stack)
	$(error unconfigured)

