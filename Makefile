.PHONY: help dev up down migrate seed test test-all openapi verify validate web-dev web-test web-build lint

PYTHON ?= python
MANAGE = $(PYTHON) manage.py

help:
	@echo "Available commands:"
	@echo "  make up         Build and start all docker-compose services (API + Web + DB + Celery)"
	@echo "  make down       Stop all docker-compose services"
	@echo "  make dev        Run local Django backend server"
	@echo "  make web-dev    Run local React frontend Vite server"
	@echo "  make migrate    Apply database migrations"
	@echo "  make seed       Seed database with demo/test fixtures"
	@echo "  make test       Run backend test suite (pytest)"
	@echo "  make web-test   Run frontend test suite (vitest)"
	@echo "  make test-all   Run both backend and frontend test suites"
	@echo "  make lint       Run linters (ruff + eslint)"
	@echo "  make openapi    Regenerate docs/openapi.json schema"
	@echo "  make verify     Run Django system checks, migration check and tests"
	@echo "  make validate   Run ML validation suite"

dev:
	$(MANAGE) runserver 0.0.0.0:8000

web-dev:
	cd web && pnpm dev

web-test:
	cd web && pnpm test

web-build:
	cd web && pnpm build

up:
	docker compose up --build

down:
	docker compose down

migrate:
	$(MANAGE) migrate --noinput

seed:
	$(MANAGE) seed

test:
	$(PYTHON) -m pytest -v

test-all:
	$(PYTHON) -m pytest -q
	cd web && pnpm test

lint:
	$(PYTHON) -m ruff check
	cd web && pnpm lint

openapi:
	$(MANAGE) spectacular --format openapi-json --file docs/openapi.json

verify:
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run
	$(PYTHON) -m pytest -q

validate:
	$(PYTHON) -m validation.run
