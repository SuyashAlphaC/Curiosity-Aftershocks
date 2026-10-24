.PHONY: setup data pipeline bulk build serve dev test check
setup:
	uv sync --locked
	cd frontend && npm ci

data:
	uv run python -m aftershocks.ingest
	uv run python -m aftershocks.pipeline

pipeline:
	uv run python -m aftershocks.pipeline

bulk:
	uv run python -m aftershocks.bulk --date 2024-04-08 --hours 18

build:
	cd frontend && npm run build

serve:
	uv run uvicorn aftershocks.api:app --host 127.0.0.1 --port 8000

dev:
	python3 scripts/dev.py

test:
	uv run pytest -q
	cd frontend && npm run test:e2e

check:
	uv run ruff check aftershocks tests
	cd frontend && npm run build

.PHONY: reproduce
reproduce:
	uv run python -m aftershocks.pipeline --raw data/reference
	cd frontend && npm run build
