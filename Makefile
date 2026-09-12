.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := backend/.venv/bin/python

.PHONY: help setup backend-setup frontend-setup clothes db dev backend frontend test lint docker clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: backend-setup clothes db frontend-setup ## Full first-time setup

backend-setup: ## Create the venv and install Python deps
	python3 -m venv backend/.venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements-dev.txt

frontend-setup: ## Install node deps + vendor MediaPipe assets
	cd frontend && npm install

clothes: ## Generate the placeholder garment PNGs
	$(PY) backend/scripts/generate_sample_clothes.py

db: ## Create tables and sync the catalog
	$(PY) backend/scripts/init_db.py

backend: ## Run the API on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run the Next.js dev server on :3000
	cd frontend && npm run dev

dev: ## Run both (backend in the background)
	@$(MAKE) -j2 backend frontend

test: ## Backend tests + frontend typecheck
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm run typecheck

docker: ## Build and start the whole stack
	docker compose up --build

clean: ## Remove generated data (keeps garment PNGs)
	rm -rf backend/data/tryon.db* backend/data/outputs frontend/.next
	rm -rf assets/clothes/.thumbs
