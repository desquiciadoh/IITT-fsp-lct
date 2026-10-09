.PHONY: help dev up down migrate seed test openapi verify validate

PYTHON ?= python
MANAGE = $(PYTHON) manage.py

help:
	@echo "Available commands:"
	@echo "  make dev       Run local development server"
	@echo "  make up        Build and start all docker-compose services"
	@echo "  make down      Stop all docker-compose services"
	@echo "  make migrate   Apply database migrations"
	@echo "  make seed      Seed database with demo/test fixtures"
	@echo "  make test      Run full automated test suite"
	@echo "  make openapi   Regenerate docs/openapi.json schema"
	@echo "  make verify    Run Django system checks, migration check and tests"
	@echo "  make validate  Run verification and test suite"

dev:
	$(MANAGE) runserver 0.0.0.0:8000

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	$(MANAGE) migrate --noinput

seed:
	$(MANAGE) seed

test:
	$(PYTHON) -m pytest -v

openapi:
	$(MANAGE) spectacular --format openapi-json --file docs/openapi.json

verify:
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run
	$(PYTHON) -m pytest -q

validate: verify
