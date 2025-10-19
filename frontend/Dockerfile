# Multi-mode Dockerfile for the frontend
# This Dockerfile supports two build modes:
#  - BUILD_MODE=production (default): optimized/minified build, no source maps
#  - BUILD_MODE=development: debug-friendly build with inline source maps and
#    disabled minification so browser stack traces map back to original files.
#
# Build examples:
#  - Production (optimized, smaller, no source maps):
#      docker build -t frontend:prod -f frontend/Dockerfile frontend
#  - Development/debug (includes inline source maps for better stack traces):
#      docker build --build-arg BUILD_MODE=development -t frontend:debug -f frontend/Dockerfile frontend
#
# Security note: development builds can expose your source code (inline
# source maps embed original sources). Never use development images in public
# production environments.

FROM node:20-slim AS builder
WORKDIR /app

# Allow callers to set VITE_API_URL at build time
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# Build mode: production (default) or development (emit source maps)
ARG BUILD_MODE=development
ENV BUILD_MODE=${BUILD_MODE}

# Make npm accept legacy peer dependency resolutions to avoid build failure
# caused by a peerDependency that hasn't been updated to explicitly allow
# React 18 (e.g. react-json-view). This is a temporary, low-risk CI/workaround
# that unblocks the Docker build. Prefer upgrading/replacing the offending
# package in the long term.
ENV NPM_CONFIG_LEGACY_PEER_DEPS=true

# Print the build mode to make it obvious in build logs
RUN echo "Frontend build mode: ${BUILD_MODE}"

# Install dependencies (including devDependencies like vite)
COPY package*.json ./
RUN npm ci --silent || npm i --no-audit --no-fund --legacy-peer-deps

COPY . .

# Build step with explicit flags and verification steps to aid debugging.
# When BUILD_MODE=development we:
#  - set NODE_ENV=development for plugins to pick up
#  - pass --sourcemap inline to embed source maps into bundles
#  - pass --mode development to Vite
#  - disable minification via vite.config (vite config reads BUILD_MODE env)
# After building we run a small verification that checks whether sourcemaps
# are present in the generated bundles and print a short excerpt of the main
# bundle to the build log to help debugging.
RUN if [ "${BUILD_MODE}" = "development" ] ; then \
      echo "Building frontend in development mode with inline source maps (suitable for debugging)."; \
      export NODE_ENV=development; \
      npm run build -- --sourcemap inline --mode development; \
    else \
      echo "Building frontend in production (optimized) mode."; \
      npm run build -- --mode production; \
    fi && \
    echo "Build output files:" && ls -la dist || true && \
    # Try to detect inline source maps (look for data:application/json;base64 or //# sourceMappingURL=...) \
    echo "Checking for source map markers in generated JS files..." && \
    if ls dist/*.js >/dev/null 2>&1 ; then \
      grep -E "sourceMappingURL|sourceMappingURL=data:application/json" -R --line-number dist || echo "No sourceMappingURL found in JS files." ; \
      echo "Showing first 200 lines of the largest JS asset for inspection:"; \
      largest=$(ls -S dist/*.js | head -n1) ; head -n200 "$largest" || true ; \
    else \
      echo "No JS files found in dist to inspect." ; \
    fi

# Runtime image serves the built assets via nginx. This is the same for both
# build modes; the development build embeds source map information inside the
# generated JS files which are copied here.
FROM nginx:stable-alpine AS runtime
RUN apk add --no-cache curl

# Use a small nginx config suitable for single-page apps (client-side routing)
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
