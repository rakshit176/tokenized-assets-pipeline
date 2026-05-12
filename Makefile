.PHONY: help install dev test lint docker-build docker-up docker-down docker-logs db-shell db-reset clean run-sample run-batch

help:
	@echo "Tokenized Assets Pipeline - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install       Install dependencies"
	@echo "  make dev           Run pipeline on default company (Securitize)"
	@echo "  make test          Run tests"
	@echo "  make lint          Run linting (ruff)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-up     Start all services"
	@echo "  make docker-down   Stop all services"
	@echo "  make docker-logs   Show service logs"
	@echo "  make docker-batch  Run batch processing from CSV"
	@echo ""
	@echo "Database:"
	@echo "  make db-shell      Open PostgreSQL shell"
	@echo "  make db-reset      Reset database (WARNING: deletes data)"
	@echo ""
	@echo "Pipeline runs:"
	@echo "  make run-sample    Run on 3 sample companies"
	@echo "  make run-batch     Run batch from companies.csv"
	@echo "  make run COMPANY='Name domain.com'  Run specific company"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove output files and caches"

install:
	pip install -r requirements.txt
	playwright install chromium --with-deps
	pre-commit install || echo "pre-commit not available"

dev:
	python step_run.py Securitize securitize.io

test:
	pytest tests/ -v --tb=short

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

docker-build:
	docker compose build

docker-up:
	docker compose up -d postgres redis searxng

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f --tail=50

docker-batch:
	docker compose -f docker-compose.batch.yml run --rm pipeline

db-shell:
	docker compose exec postgres psql -U fiftyone -d fiftyone_insight

db-reset:
	docker compose exec postgres psql -U fiftyone -d fiftyone_insight -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	docker compose exec postgres psql -U fiftyone -d fiftyone_insight -f /docker-entrypoint-initdb.d/01_schema.sql

run-sample:
	python step_run.py Securitize securitize.io "Ondo Finance" ondo.finance Centrifuge centrifuge.io

run-batch:
	python scripts/batch_run.py companies.csv

run:
	@if [ -z "$(COMPANY)" ]; then \
		echo "Usage: make run COMPANY='Name domain.com'"; \
		exit 1; \
	fi
	python step_run.py $(COMPANY)

clean:
	rm -rf output/*.json output/*.xlsx output/*.txt
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .playwright
