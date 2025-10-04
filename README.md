```json
{'project_name': 'no_code_ai_assistant', 'backend': 'fastapi', 'frontend': 'react', 'database': 'postgres', 'include_docker': True, 'include_tailwind': False, 'backend_port': 8000, 'frontend_port': 3000, 'include_precommit': True, 'include_alembic': False, 'include_helm': False, 'include_terraform': False, 'dry_run': False, 'on_exists': 'overwrite'}
```

## Development

Run the development stack with Docker Compose (this will start the backend, frontend, Postgres, Redis, and a Celery worker):

```bash
docker-compose up --build
```

Environment variables:
- SECRETS_KEY: encryption key used to encrypt workspace secrets (default placeholder in docker-compose). Replace in production.

