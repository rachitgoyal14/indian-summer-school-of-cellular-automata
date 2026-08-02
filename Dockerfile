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

# Configure Nginx for single-container deployment (proxying /ws & /health to local backend)
RUN echo 'server {' > /etc/nginx/sites-available/default && \
    echo '    listen 80;' >> /etc/nginx/sites-available/default && \
    echo '    server_name _;' >> /etc/nginx/sites-available/default && \
    echo '    root /usr/share/nginx/html;' >> /etc/nginx/sites-available/default && \
    echo '    index index.html;' >> /etc/nginx/sites-available/default && \
    echo '    gzip on;' >> /etc/nginx/sites-available/default && \
    echo '    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;' >> /etc/nginx/sites-available/default && \
    echo '    location / {' >> /etc/nginx/sites-available/default && \
    echo '        try_files $$uri $$uri/ /index.html;' >> /etc/nginx/sites-available/default && \
    echo '        add_header Cache-Control "no-cache";' >> /etc/nginx/sites-available/default && \
    echo '    }' >> /etc/nginx/sites-available/default && \
    echo '    location /ws {' >> /etc/nginx/sites-available/default && \
    echo '        proxy_pass http://127.0.0.1:8000;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_http_version 1.1;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header Upgrade $$http_upgrade;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header Connection "upgrade";' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header Host $$host;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header X-Real-IP $$remote_addr;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header X-Forwarded-For $$proxy_add_x_forwarded_for;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header X-Forwarded-Proto $$scheme;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_connect_timeout 7d;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_send_timeout 7d;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_read_timeout 7d;' >> /etc/nginx/sites-available/default && \
    echo '    }' >> /etc/nginx/sites-available/default && \
    echo '    location /health {' >> /etc/nginx/sites-available/default && \
    echo '        proxy_pass http://127.0.0.1:8000/health;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header Host $$host;' >> /etc/nginx/sites-available/default && \
    echo '        proxy_set_header X-Real-IP $$remote_addr;' >> /etc/nginx/sites-available/default && \
    echo '    }' >> /etc/nginx/sites-available/default && \
    echo '    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$$ {' >> /etc/nginx/sites-available/default && \
    echo '        expires 1y;' >> /etc/nginx/sites-available/default && \
    echo '        add_header Cache-Control "public, immutable";' >> /etc/nginx/sites-available/default && \
    echo '    }' >> /etc/nginx/sites-available/default && \
    echo '}' >> /etc/nginx/sites-available/default

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
ENV CA_HOST=0.0.0.0
ENV CA_PORT=8000

CMD ["sh", "-c", "nginx && python backend/scripts/run_server.py"]

EXPOSE 80 8000
