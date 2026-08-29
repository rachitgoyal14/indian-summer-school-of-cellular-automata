#!/bin/sh
set -e

PORT="${PORT:-80}"
echo "[Entrypoint] Starting container on port ${PORT}..."

# Generate Nginx configuration dynamically with $PORT
cat <<EOF > /etc/nginx/sites-available/default
server {
    listen ${PORT};
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    location / {
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Forward nginx logs to stdout/stderr for cloud log aggregators (Railway, GCP, etc.)
ln -sf /dev/stdout /var/log/nginx/access.log
ln -sf /dev/stderr /var/log/nginx/error.log

# Verify Nginx configuration
nginx -t

# Start Nginx in background
echo "[Entrypoint] Starting Nginx on port ${PORT}..."
nginx

# Set backend env vars
export CA_HOST=127.0.0.1
export CA_PORT=8000
export PYTHONPATH=/app/backend

echo "[Entrypoint] Starting Python backend on 127.0.0.1:8000..."
exec python backend/scripts/run_server.py
