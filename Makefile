.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV     := .venv
PYTHON   := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
PROTO_SRC := proto/agent.proto

# ──────────────────────────────────────────────
# Environment
# ──────────────────────────────────────────────

.PHONY: install
install: ## Create venv and install dev dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo "✓ Run 'source $(VENV)/bin/activate' to activate the venv"

# ──────────────────────────────────────────────
# Docker Compose
# ──────────────────────────────────────────────

.PHONY: up
up: ## Start all services (docker compose up --build -d)
	docker compose up --build -d

.PHONY: down
down: ## Stop all services
	docker compose down

.PHONY: restart
restart: down up ## Restart all services

.PHONY: logs
logs: ## Tail docker compose logs
	docker compose logs -f

# ──────────────────────────────────────────────
# Code generation
# ──────────────────────────────────────────────

.PHONY: proto
proto: ## Regenerate gRPC stubs from proto/agent.proto
	$(PYTHON) -m grpc_tools.protoc \
		-I. \
		--python_out=. \
		--grpc_python_out=. \
		$(PROTO_SRC)
	@echo "✓ Proto stubs regenerated"

# ──────────────────────────────────────────────
# Quality checks
# ──────────────────────────────────────────────

.PHONY: lint
lint: ## Run ruff linter
	$(PYTHON) -m ruff check .

.PHONY: fmt
fmt: ## Format code with ruff
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

.PHONY: typecheck
typecheck: ## Run mypy type checker
	$(PYTHON) -m mypy services/ legacy/

.PHONY: test
test: ## Run pytest
	$(PYTHON) -m pytest -v

.PHONY: check
check: lint typecheck test ## Run all checks (lint + typecheck + test)

# ──────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info
	rm -rf .mypy_cache .ruff_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ──────────────────────────────────────────────
# Help
# ──────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
