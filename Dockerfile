# Backend: Builder stage (wheels)
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
# copy backend into /app/backend so the package name `backend` is importable from /app
COPY ./backend /app/backend
RUN python -m pip install --upgrade pip setuptools wheel
# build wheels from backend/requirements.txt
RUN pip wheel --no-cache-dir -r backend/requirements.txt -w /wheels

# Backend: Runtime
FROM python:3.11-slim AS backend_runtime
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

# Frontend: build using node and produce a small nginx runtime image
FROM node:20-slim AS frontend_builder
WORKDIR /app/frontend
# Allow callers to set NODE_ENV and VITE_API_URL at build time
# Default to development so devDependencies (vite) are available for the build
ARG NODE_ENV=development
ENV NODE_ENV=${NODE_ENV}
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# Copy frontend sources and install
COPY ./frontend /app/frontend
# Ensure devDependencies (vite) are installed for the build stage
RUN npm ci --silent || npm i --no-audit --no-fund

# Build the frontend
RUN npm run build

# Frontend runtime image
FROM nginx:stable-alpine AS frontend_runtime
RUN apk add --no-cache curl

# Use a small nginx config suitable for single-page apps (client-side routing)
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static files from the frontend builder
COPY --from=frontend_builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
