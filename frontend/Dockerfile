# Frontend Dockerfile for CA Rule 184 Traffic Simulator
# Multi-stage build for optimized production image

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the app
RUN npm run build

# Stage 2: Production with nginx
FROM nginx:alpine

# Install gettext for envsubst (not always present in nginx:alpine)
RUN apk add --no-cache gettext

# Copy custom nginx config template
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Use a startup script to substitute environment variables with explicit scoping
# This prevents nginx's own variables ($uri, $host, $http_upgrade, etc.) from being corrupted
RUN echo '#!/bin/sh' > /docker-entrypoint.d/40-envsubst-on-templates.sh && \
    echo 'set -e' >> /docker-entrypoint.d/40-envsubst-on-templates.sh && \
    echo 'export PORT="${PORT:-80}"' >> /docker-entrypoint.d/40-envsubst-on-templates.sh && \
    echo 'export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"' >> /docker-entrypoint.d/40-envsubst-on-templates.sh && \
    echo 'envsubst '"'"'${PORT} ${BACKEND_URL}'"'"' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf' >> /docker-entrypoint.d/40-envsubst-on-templates.sh && \
    echo 'echo "Nginx configured to listen on port $PORT and proxy to $BACKEND_URL"' >> /docker-entrypoint.d/40-envsubst-on-templates.sh && \
    chmod +x /docker-entrypoint.d/40-envsubst-on-templates.sh

# Start nginx (the entrypoint scripts will run automatically)
CMD ["nginx", "-g", "daemon off;"]
