# No-code AI Assistant (n8n-like)

This repository contains a prototype no-code AI assistant platform (n8n-style) with a FastAPI backend, React frontend (react-flow for the visual editor), Celery workers, Redis broker, Postgres, and optional MinIO for artifact storage.

This README describes how to build, run, develop, test, and release the application.

Requirements
- Docker & Docker Compose (v1.29+ or v2)
- Node 16+ / npm 8+ (for frontend development)
- Python 3.11+ (for running tests locally)
- Windows users: Make is not required. See "Windows development" below.

Quickstart (development)
1. Copy environment example and edit as needed:
   - cp .env.example .env    # Linux / macOS / WSL
   - copy .env.example .env  # Windows CMD
   - powershell -Command "Copy-Item .env.example .env"  # PowerShell
   - Edit variables in .env (database URL, SECRETS_KEY, etc.)

2. Build and start the stack:
   - make build
   - make up
   - or: docker-compose up --build

3. Visit services:
   - Backend API: http://localhost:8000
   - Frontend: http://localhost:3000

Local development (backend)
- Enter the backend container (recommended to use venv locally instead of container):
  - cd backend
  - python -m venv .venv
  - source .venv/bin/activate    # or .venv\Scripts\activate on Windows
  - pip install -r requirements.txt
  - uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

Local development (frontend)
- cd frontend
- npm ci
- npm start
- The frontend dev server runs on http://localhost:3000 and proxies API calls to the backend in dev compose.

Running tests
- Backend unit tests (in-memory SQLite):
  - cd backend
  - pytest -q

Makefile commands
- make build: docker-compose build
- make up: docker-compose up -d --remove-orphans
- make down: docker-compose down
- make logs: docker-compose logs -f
- make frontend-build: builds the frontend production bundle
- make backend-build: builds backend Docker image
- make test: runs backend tests
- make release VERSION=0.1.0 REGISTRY=your.registry.com/yourrepo: run a simple release flow (build & tag)

Windows development
- If you don't want to install make on Windows, use the provided scripts in scripts/windows/ (batch files) which mirror the Makefile targets.

Quick PowerShell examples (useful if you prefer PowerShell over the batch files)
1) Build
- Backend (Docker image build via docker-compose):
  docker-compose build --no-cache web
- Frontend (npm):
  cd frontend
  npm ci
  npm run build
  cd ..

2) Start dev (compose)
- docker-compose up --build

3) Stop / clean
- docker-compose down --volumes --remove-orphans

4) Tests (backend)
- cd backend
- python -m venv .venv
- .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt
- pytest -q

Batch scripts available (scripts/windows/*.bat)
- build.bat          — docker-compose build
- up.bat             — docker-compose up --build
- down.bat           — docker-compose down --volumes --remove-orphans
- test.bat           — create venv, install deps, run pytest (backend)
- frontend-build.bat — install frontend deps and build
- backend-build.bat  — build backend Docker image
- release.bat        — build & optionally tag/push images (pass VERSION and optional REGISTRY as arguments)

Examples (Command Prompt)
- Start dev stack:
  scripts\windows\up.bat

- Run tests:
  scripts\windows\test.bat

Environment variables
- See .env.example for variables used by docker-compose and services. Key variables include:
  - DATABASE_URL
  - REDIS_URL
  - SECRETS_KEY
  - ENABLE_LIVE_LLM (default false)
  - CELERY_BROKER_URL

Secrets & Keys
- SECRETS_KEY is used to derive an encryption key for storing secrets. In production, use a secure KMS and rotate keys regularly.
- Never commit secrets to the repository.

Releasing / Production notes
- The Makefile includes a release target that tags and (optionally) pushes images to a registry.
- For production, we recommend building images, pushing to a registry, and deploying via Kubernetes or your preferred orchestrator (Helm manifests are not included yet).
- Ensure you configure a KMS-backed secrets store and set ENABLE_LIVE_LLM in production only if you intend to make real LLM calls.

Spec and roadmap
- specs/README_SPEC.md contains the living spec and checklist for this project.

Support
- If you encounter issues running the stack, check docker-compose logs for web and worker and verify your environment variables.