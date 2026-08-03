# Backend Dockerfile for CA Rule 184 Traffic Simulator
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire backend source
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV CA_HOST=0.0.0.0

# Railway injects PORT dynamically - map it to CA_PORT for the backend script
# Default to 8000 for local development if PORT is not set
CMD sh -c 'CA_PORT=${PORT:-8000} python scripts/run_server.py'
