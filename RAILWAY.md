# Railway Deployment Guide

## Overview

This guide covers deploying the CA Rule 184 Traffic Simulator to Railway. Unlike Docker Compose, Railway deploys each service (backend and frontend) **independently** in separate containers with their own URLs and environment variables.

**Key differences from Docker Compose deployment:**
- Services are deployed independently, not orchestrated together
- Railway injects a dynamic `$PORT` variable each service must listen on
- Services communicate via Railway's internal networking (`*.railway.internal`)
- No `docker-compose.yml` orchestration—each service has its own Dockerfile and `railway.json`

---

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app/)
2. **Railway CLI** (optional but recommended): 
   ```bash
   npm install -g @railway/cli
   railway login
   ```
3. **Git repository**: Push this code to GitHub/GitLab (Railway can deploy from git)

---

## Deployment Steps

### Step 1: Create a New Railway Project

1. Go to [railway.app/new](https://railway.app/new)
2. Click **"+ New Project"**
3. Select **"Deploy from GitHub repo"** (or use CLI: `railway init`)
4. Select this repository

### Step 2: Deploy the Backend Service

1. In your Railway project dashboard, click **"+ New Service"**
2. Select **"GitHub Repo"** and choose this repository
3. Configure the backend service:
   - **Service Name**: `backend` (or any name you prefer)
   - **Root Directory**: `backend`
   - **Builder**: Railway will automatically detect `railway.json` and use the Dockerfile
4. Railway will automatically inject the `PORT` environment variable—**no manual configuration needed**
5. Click **"Deploy"**
6. Once deployed, note the **internal URL** shown in the service settings. It will be something like:
   ```
   backend.railway.internal
   ```
   Or you can reference it via the service name Railway assigns.

### Step 3: Deploy the Frontend Service

1. Click **"+ New Service"** again
2. Select the same GitHub repository
3. Configure the frontend service:
   - **Service Name**: `frontend` (or any name you prefer)
   - **Root Directory**: `frontend`
   - **Builder**: Railway will automatically detect `railway.json` and use the Dockerfile
4. **Add Environment Variable**:
   - Click **"Variables"** tab
   - Add variable:
     - **Name**: `BACKEND_URL`
     - **Value**: `http://backend.railway.internal:${{backend.PORT}}`
     
     *Replace `backend` with the exact service name you gave the backend in Step 2.*
     
     Railway's variable interpolation syntax `${{service-name.PORT}}` automatically injects the backend's assigned port.
     
     **Alternative**: If Railway provides a private URL for the backend service, you can use that full URL instead:
     ```
     http://backend-production-xxxx.railway.internal
     ```
5. Railway will automatically inject the `PORT` variable for the frontend too—**no manual configuration needed**
6. Click **"Deploy"**

### Step 4: Generate Public URL for Frontend

1. Go to the **frontend service settings**
2. Click **"Settings"** → **"Networking"**
3. Click **"Generate Domain"**
4. Railway will generate a public URL like: `https://your-app.up.railway.app`
5. Open this URL in your browser to access the simulator

---

## Environment Variables Summary

### Backend Service

| Variable | Set By | Value | Notes |
|----------|--------|-------|-------|
| `PORT` | Railway (automatic) | Random high port | Backend listens on this dynamically |

### Frontend Service

| Variable | Set By | Value | Notes |
|----------|--------|-------|-------|
| `PORT` | Railway (automatic) | Random high port | Nginx listens on this dynamically |
| `BACKEND_URL` | **You (manual)** | `http://backend.railway.internal:${{backend.PORT}}` | URL where nginx proxies `/ws` and `/health` requests |

---

## Architecture on Railway

```
┌─────────────────────────────────────────────────────────┐
│  Railway Load Balancer (public internet)                │
│  https://your-app.up.railway.app                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  Frontend Service      │
         │  (Nginx + React SPA)   │
         │  Listens on: $PORT     │──┐
         │  (Railway-injected)    │  │
         └───────────────────────┘  │
                     │               │
            Proxies /ws & /health    │
                     │               │
                     ▼               │
         ┌───────────────────────┐  │ Railway Internal
         │  Backend Service       │  │ Network
         │  (FastAPI + WebSocket) │  │ (*.railway.internal)
         │  Listens on: $PORT     │◄─┘
         │  (Railway-injected)    │
         └───────────────────────┘
```

**Key Points:**
- Frontend proxies WebSocket (`/ws`) and API (`/health`) requests to the backend via Railway's internal network
- Each service listens on Railway's dynamically assigned `$PORT`
- Only the frontend service has a public URL generated; backend is private by default

---

## Verifying Deployment

1. **Check backend health** (if you generate a public domain for backend):
   ```bash
   curl https://backend-service.up.railway.app/health
   ```
   Should return: `{"status": "healthy"}`

2. **Open frontend**: Navigate to your frontend's Railway URL
3. **Test WebSocket**: Open browser DevTools → Network → WS tab, verify WebSocket connection to `/ws` is established
4. **Test simulation**: Click "Start Simulation" and verify live traffic updates

---

## Troubleshooting

### "Application failed to respond" Error

**Cause**: Service is not listening on the Railway-injected `$PORT`.

**Solution**: 
- Backend: Verify `backend/Dockerfile` CMD uses `CA_PORT=${PORT:-8000}`
- Frontend: Verify `frontend/Dockerfile` runs envsubst to substitute `${PORT}` in nginx.conf

### WebSocket Connection Fails

**Cause**: `BACKEND_URL` environment variable not set correctly on frontend service.

**Solution**:
- Go to frontend service settings → Variables
- Verify `BACKEND_URL` is set to `http://backend.railway.internal:${{backend.PORT}}`
- Ensure the service name matches your backend service name exactly

### Nginx Variables Corrupted ("invalid variable name")

**Cause**: Unscoped `envsubst` is replacing nginx's built-in variables (`$uri`, `$host`, etc.) with empty strings.

**Solution**:
- Verify `frontend/Dockerfile` uses **scoped envsubst**:
  ```bash
  envsubst '${PORT} ${BACKEND_URL}' < template > output
  ```
- The single quotes around `'${PORT} ${BACKEND_URL}'` are critical—they tell envsubst to **only** substitute those two variables.

### Backend Logs Show "Address already in use"

**Cause**: Multiple instances trying to bind to same port (shouldn't happen on Railway).

**Solution**:
- Check Railway service settings → **Instances**: ensure only 1 instance is running (default)
- Restart the service

---

## Railway-Specific Files

This repository includes the following Railway configuration files:

- **`backend/railway.json`**: Pins backend to use Dockerfile builder (prevents Nixpacks auto-detection)
- **`frontend/railway.json`**: Pins frontend to use Dockerfile builder (prevents Nixpacks auto-detection)

These files ensure Railway uses the custom Dockerfiles instead of attempting to auto-detect build settings with Nixpacks.

---

## Cost Considerations

- **Free Tier**: Railway provides $5 of free usage per month
- **Typical usage**: Frontend (~0.1 vCPU) + Backend (~0.2 vCPU) = ~$10-15/month
- **Optimization**: Set sleep/auto-pause for services if not in active use

---

## Updating Deployment

When you push changes to your GitHub repository:

1. Railway automatically detects the commit
2. Each affected service rebuilds and redeploys automatically
3. Zero-downtime deployment (Railway keeps old version running until new one is healthy)

To manually redeploy:
```bash
railway up -s backend
railway up -s frontend
```

---

## Differences from Docker Compose (Local Development)

| Aspect | Docker Compose | Railway |
|--------|---------------|---------|
| **Orchestration** | Single `docker-compose.yml` | Independent services |
| **Networking** | Service names (e.g., `http://backend:8000`) | `*.railway.internal` + interpolated ports |
| **Ports** | Fixed (8000, 80) | Dynamic `$PORT` injection |
| **Health checks** | `depends_on: condition: service_healthy` | Not supported (services start independently) |
| **Local dev** | `docker compose up` | Each Dockerfile works independently with defaults |

---

## Support

- **Railway Docs**: [docs.railway.app](https://docs.railway.app/)
- **Discord**: [Railway Community Discord](https://discord.gg/railway)

---

## License

MIT
