# Simple Makefile for development
HEALTH_INTERVAL ?= 10s
HEALTH_TIMEOUT ?= 5s
HEALTH_RETRIES ?= 5

.PHONY: build up down logs frontend-build backend-build test lint format clean release

build:
	docker-compose build

up:
	HEALTH_INTERVAL=$(HEALTH_INTERVAL) HEALTH_TIMEOUT=$(HEALTH_TIMEOUT) HEALTH_RETRIES=$(HEALTH_RETRIES) docker-compose up -d --remove-orphans

down:
	docker-compose down

logs:
	docker-compose logs -f

frontend-build:
	@cd frontend && (npm ci || npm i --no-audit --no-fund) && npm run build

backend-build:
	@docker build -t no_code_ai_assistant-backend -f backend/Dockerfile backend

test:
	@echo "Running backend tests..."
	@cd backend && pytest -q

lint:
	@echo "No linter configured yet. Add lint commands here."

format:
	@echo "No formatter configured yet. Add format commands here."

clean:
	docker-compose down --volumes --remove-orphans
	rm -rf .pytest_cache

release:
	@echo "Release helper. Example usage: make release VERSION=0.1.0 REGISTRY=your.registry.com/yourrepo"
	@if [ -z "$(VERSION)" ]; then echo "VERSION is required (e.g. make release VERSION=0.1.0)"; exit 1; fi
	@if [ -z "$(REGISTRY)" ]; then echo "REGISTRY not set; defaulting to local tags"; fi
	@echo "Building images..."
	@docker-compose build --no-cache
	@echo "Tagging images..."
	@IMAGE_BACKEND_TAG=$(REGISTRY)/no_code_ai_assistant-backend:$(VERSION) || true
	@docker tag no_code_ai_assistant-backend:latest $(IMAGE_BACKEND_TAG) || true
	@echo "Push images if REGISTRY provided..."
	@if [ -n "$(REGISTRY)" ]; then docker push $(IMAGE_BACKEND_TAG); fi
	@echo "Release complete."
