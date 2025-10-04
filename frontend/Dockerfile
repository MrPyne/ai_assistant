FROM node:20-slim AS builder
WORKDIR /app

# Allow callers to set NODE_ENV and VITE_API_URL at build time
ARG NODE_ENV=production
ENV NODE_ENV=${NODE_ENV}
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# Install dependencies
COPY package*.json ./
RUN npm ci --silent || npm i --no-audit --no-fund

# Copy sources and build
COPY . .
RUN npm run build

# Production image
FROM nginx:stable-alpine
RUN apk add --no-cache curl

# Use a small nginx config suitable for single-page apps (client-side routing)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static files
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
