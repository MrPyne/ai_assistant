# Builder
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
# copy backend into /app/backend so the package name `backend` is importable from /app
COPY ./backend /app/backend
RUN python -m pip install --upgrade pip setuptools wheel
# build wheels from backend/requirements.txt
RUN pip wheel --no-cache-dir -r backend/requirements.txt -w /wheels

# Runtime
FROM python:3.11-slim
RUN groupadd -r app && useradd -r -g app app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
RUN pip install --no-cache /wheels/* || true
# copy the backend package into /app/backend so it can be imported as `backend`
COPY --chown=app:app ./backend /app/backend
# copy the python wait helper to avoid shell shebang issues
COPY --chown=app:app backend/wait_for_db.py /app/wait_for_db.py
# remove any shell-based wait scripts from the image to avoid CRLF/shebang issues
RUN rm -f /app/backend/wait-for-db.sh || true
ENV PORT=8000
EXPOSE 8000
USER app
# use the python wait helper to avoid CRLF issues and exec uvicorn
CMD ["python", "/app/wait_for_db.py"]
