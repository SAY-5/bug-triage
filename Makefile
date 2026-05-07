.PHONY: dev install migrate seed index test test-property bench bench-regress lint typecheck eval eval-smoke java-build up down clean

POETRY ?= poetry
PYTHON ?= $(POETRY) run python

install:
	$(POETRY) install --with dev

dev:
	$(POETRY) install --with dev,embeddings,providers

migrate:
	$(POETRY) run alembic upgrade head

seed:
	$(POETRY) run python scripts/seed.py

index:
	$(POETRY) run bug-triage index

test:
	$(POETRY) run pytest -q

test-cov:
	$(POETRY) run pytest --cov=bug_triage --cov-report=term-missing

test-property:
	HASH_EMBEDDER=1 $(POETRY) run pytest tests/property -q

bench:
	HASH_EMBEDDER=1 $(POETRY) run python -m bench.harness

bench-regress:
	HASH_EMBEDDER=1 $(POETRY) run python -m bench.regress

lint:
	$(POETRY) run ruff check src tests
	$(POETRY) run black --check src tests

format:
	$(POETRY) run ruff check --fix src tests
	$(POETRY) run black src tests

typecheck:
	$(POETRY) run mypy

eval:
	$(POETRY) run bug-triage eval run --suite triage_v1 --provider fake --output eval/baselines/triage_fake.json

eval-smoke:
	RUN_EVAL_SMOKE=1 $(POETRY) run pytest tests/eval -q

java-build:
	cd corpus/target && mvn -B verify

up:
	docker compose up -d --build

down:
	docker compose down -v

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
