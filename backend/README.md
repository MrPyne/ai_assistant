Development

Start services via docker-compose (requires Docker):

  docker-compose up --build

Backend (FastAPI) will be available at http://localhost:8000

Environment variables
- DATABASE_URL: SQLAlchemy database url
- SECRET_KEY: JWT secret

Run tests:

  pytest -q
