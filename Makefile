.PHONY: dev backend frontend test

BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173
BACKEND_URL ?= http://127.0.0.1:$(BACKEND_PORT)

.DEFAULT_GOAL := dev

dev: .env
	$(MAKE) -j2 backend frontend

.env:
	cp .env.example .env

backend:
	cd backend && uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port $(BACKEND_PORT)

frontend:
	cd frontend && BACKEND_URL=$(BACKEND_URL) npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT)

test:
	cd backend && uv run pytest
	cd frontend && npm test && npm run theme:check
