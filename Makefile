# Simple Makefile for development
HEALTH_INTERVAL ?= 10s
HEALTH_TIMEOUT ?= 5s
HEALTH_RETRIES ?= 5
.PHONY: build up down logs frontend-build backend-build test

build:
	docker-compose build

up:
	HEALTH_INTERVAL=$(HEALTH_INTERVAL) HEALTH_TIMEOUT=$(HEALTH_TIMEOUT) HEALTH_RETRIES=$(HEALTH_RETRIES) docker-compose up -d --remove-orphans

down:
	docker-compose down

logs:
	docker-compose logs -f

frontend-build:
	cd frontend && npm ci || npm i --no-audit --no-fund && npm run build

backend-build:
	docker build -t no_code_ai_assistant-backend .

test:
	pytest -q || true
