# Unified Dockerfile for CA Rule 184 Traffic Simulator
# Builds frontend and packages both backend (FastAPI) and frontend (Nginx) in a single container.

# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Final Production Environment
FROM python:3.12-slim

# Install Nginx and required tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements & install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application source
COPY backend/ ./backend/

# Copy built frontend static files to Nginx web root
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html

# Copy entrypoint script for dynamic $PORT binding and startup
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

EXPOSE 80

ENTRYPOINT ["/app/docker-entrypoint.sh"]
