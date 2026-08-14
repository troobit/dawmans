# Development tooling entry point. When a Makefile exists, `make <target>` is the
# canonical way to build/test/lint — fill in the TODO targets once the stack is chosen.

.DEFAULT_GOAL := help
.PHONY: help build test lint spelling clean new-project

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the project (TODO: configure for the chosen stack)
	$(error unconfigured)

test: ## Run the tests (TODO: configure for the chosen stack)
	$(error unconfigured)

lint: spelling ## Run linters (spelling today; add stack linters when chosen)

spelling: ## Check spelling
	bash tools/check_spelling.sh

clean: ## Remove build artefacts (TODO: configure for the chosen stack)
	$(error unconfigured)

