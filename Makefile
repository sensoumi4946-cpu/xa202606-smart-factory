.PHONY: up down test lint clean install-dev generate-adapters check-generated

install-dev:
	pip install -e shared/
	pip install -e backend/[dev]
	pip install -e connectivity/[dev]
	pip install -e analytics/[dev]
	pip install -e semantic-layer/[dev]
	cd dashboard && npm install

generate-adapters:
	python scripts/generate_adapters.py

check-generated:
	python scripts/generate_adapters.py --check

up:
	docker compose -f deploy/docker-compose.yml up -d

down:
	docker compose -f deploy/docker-compose.yml down

test:
	pip install -e shared/ 2>/dev/null
	pip install -e backend/[dev] 2>/dev/null
	pip install -e connectivity/[dev] 2>/dev/null
	pip install -e analytics/[dev] 2>/dev/null
	pip install -e semantic-layer/[dev] 2>/dev/null
	cd backend  && python -m pytest tests/ -v
	cd connectivity && python -m pytest tests/ -v
	cd analytics && python -m pytest tests/ -v
	cd shared  && python -m pytest tests/ -v
	cd semantic-layer && python -m pytest tests/ -v
	cd dashboard && npx vitest run 2>/dev/null || npm test

lint:
	cd backend  && ruff check src/ && ruff format --check src/
	cd connectivity && ruff check src/ && ruff format --check src/
	cd analytics && ruff check src/ && ruff format --check src/
	cd shared  && ruff check src/ && ruff format --check src/
	cd semantic-layer && ruff check src/ && ruff format --check src/

clean:
	rm -rf backend/data/
	rm -rf dashboard/node_modules/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
