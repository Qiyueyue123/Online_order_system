.PHONY: legacy api web local local-down db-up migrate seed test lint openapi

local:
	docker compose up --build

local-down:
	docker compose down

legacy:
	.venv/bin/python run.py

db-up:
	docker compose up -d postgres

migrate:
	cd apps/api && ../../.venv/bin/alembic upgrade head

seed:
	cd apps/api && ../../.venv/bin/python -m app.seed

api:
	cd apps/api && ../../.venv/bin/uvicorn app.main:app --reload --port 8001

web:
	cd apps/web && npm run dev

test:
	.venv/bin/pytest tests
	cd apps/api && ../../.venv/bin/pytest
	cd apps/web && npm test

lint:
	cd apps/api && ../../.venv/bin/ruff check .
	cd apps/web && npm run lint

openapi:
	cd apps/api && ../../.venv/bin/python -c "import json; from app.main import app; open('openapi.json','w').write(json.dumps(app.openapi(),indent=2))"
	cd apps/web && npm run generate:api
