# Deployment Guide

This project supports two deployment options:
1. **Option 1: 1-Click Unified Railway Deployment (Recommended)** — Deploys the complete application (Frontend + Backend) in a single service on Railway.
2. **Option 2: Split Deployment** — Backend on Railway + Frontend on Vercel.

---

## ⚡ Option 1: 1-Click Unified Railway Deployment (Recommended)

When you connect this repository to Railway, Railway will automatically detect [`railway.json`](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/railway.json) and [`Dockerfile`](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/Dockerfile) at the root.

### Steps:
1. Go to [railway.app/new](https://railway.app/new) and select **"Deploy from GitHub repo"**.
2. Select this repository.
3. Railway builds the unified container:
   - Builds the React + PixiJS frontend.
   - Sets up Nginx reverse proxy dynamically bound to Railway's dynamic `$PORT`.
   - Boots the FastAPI WebSocket backend.
   - Healthcheck `/health` passes automatically.
4. Go to **Settings** → **Networking** → **Public Networking** and click **"Generate Domain"**.
5. Open your generated domain (e.g., `https://your-app.up.railway.app`) in your browser. The frontend and backend communicate seamlessly via same-origin WebSocket (`wss://.../ws`).

---

## Option 2: Split Deployment Architecture (Railway Backend + Vercel Frontend)

### Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app/)
2. **Vercel Account**: Sign up at [vercel.com](https://vercel.com/)
3. **Git Repository**: Push this code to GitHub/GitLab

---

### Deployment Order

**IMPORTANT:** Deploy the backend FIRST, then the frontend. The frontend build requires the backend's Railway URL to be set as an environment variable before building.

---

## Part 1: Deploy Backend to Railway

### Step 1: Create Railway Project

1. Go to [railway.app/new](https://railway.app/new)
2. Click **"+ New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose this repository
5. Railway will prompt you to configure the service

### Step 2: Configure Backend Service

1. **Service Name**: `backend` (or any name you prefer)
2. **Root Directory**: Set to `backend`
   - Click **Settings** → **Source** → **Root Directory** → Enter `backend`
3. **Builder**: Railway will automatically detect `backend/railway.json` and use the Dockerfile
4. Railway automatically injects the `PORT` environment variable — no manual configuration needed

### Step 3: Optional - Lock Down CORS (Recommended for Production)

By default, the backend accepts requests from any origin (`ALLOWED_ORIGINS=*`). Once you have the Vercel frontend URL, lock this down:

1. Go to backend service **Variables** tab
2. Add environment variable:
   - **Name**: `ALLOWED_ORIGINS`
   - **Value**: `https://your-app.vercel.app,https://your-app-git-branch.vercel.app`
   
   You can specify multiple comma-separated origins to allow both production and preview deployments.

### Step 4: Get Backend WebSocket URL

1. Once deployed, go to **Settings** → **Networking** → **Public Networking**
2. Click **"Generate Domain"** if no domain exists
3. Note the generated URL, e.g., `https://backend-production-xxxx.railway.app`
4. **Your WebSocket endpoint will be**: `wss://backend-production-xxxx.railway.app/ws`
   - Note: Use `wss://` (secure WebSocket) not `ws://`

### Step 5: Verify Backend Health

Test the health endpoint:
```bash
curl https://backend-production-xxxx.railway.app/health
```

Expected response:
```json
{"status": "ok", ...}
```

---

## Part 2: Deploy Frontend to Vercel

### Step 1: Create Vercel Project

1. Go to [vercel.com/new](https://vercel.com/new)
2. Click **"Import Project"**
3. Select **"Import Git Repository"** and choose this repository
4. Vercel will auto-detect it as a Vite project

### Step 2: Configure Build Settings

1. **Project Name**: Choose a name (e.g., `ca-traffic-simulator`)
2. **Framework Preset**: Vite (auto-detected)
3. **Root Directory**: Set to `frontend`
   - Click **"Edit"** next to Root Directory
   - Enter `frontend`
4. **Build Command**: `npm run build` (default, no change needed)
5. **Output Directory**: `dist` (default, no change needed)

### Step 3: Set Environment Variables ⚠️ CRITICAL

**Before deploying**, add the backend WebSocket URL:

1. Click **"Environment Variables"** section
2. Add variable:
   - **Name**: `VITE_BACKEND_WS_URL`
   - **Value**: `wss://backend-production-xxxx.railway.app/ws`
     - Replace with your actual Railway backend URL from Part 1, Step 4
     - Must use `wss://` (secure WebSocket)
     - Must include `/ws` endpoint path
3. **Environments**: Select all environments (Production, Preview, Development)

### Step 4: Deploy

1. Click **"Deploy"**
2. Vercel will build and deploy the frontend
3. Wait for deployment to complete (~1-2 minutes)

### Step 5: Get Frontend URL

1. Once deployed, Vercel shows your production URL: `https://your-app.vercel.app`
2. Open this URL in your browser
3. The simulator should load and connect to the Railway backend

---

## Verification Checklist

After both deployments complete:

### ✅ Backend Verification
- [ ] Health endpoint responds: `curl https://<railway-url>/health`
- [ ] WebSocket endpoint is accessible (check browser DevTools → Network → WS tab)
- [ ] Backend logs show no CORS errors

### ✅ Frontend Verification
- [ ] Site loads without 404 errors
- [ ] Browser DevTools → Console shows no errors
- [ ] Browser DevTools → Network → WS tab shows successful WebSocket connection
- [ ] Simulator controls respond (Start/Pause/Reset)
- [ ] Traffic animation renders smoothly

### ✅ Connection Verification
1. Open browser DevTools → Network → WS filter
2. You should see: `wss://<railway-url>/ws` with status **101 Switching Protocols**
3. Messages tab should show JSON messages flowing between frontend and backend
4. If connection fails:
   - Check `VITE_BACKEND_WS_URL` is set correctly in Vercel
   - Check Railway backend logs for CORS or port issues
   - Verify Railway domain is publicly accessible (not private networking)

---

## Environment Variables Reference

### Backend (Railway)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No (auto-injected by Railway) | 8000 | Port the backend listens on |
| `ALLOWED_ORIGINS` | Optional | `*` | Comma-separated list of allowed CORS origins. Set to Vercel domain(s) for security. |
| `CA_HOST` | Optional | `0.0.0.0` | Host to bind to (must be `0.0.0.0` for Railway) |

**Example production CORS configuration:**
```
ALLOWED_ORIGINS=https://ca-traffic.vercel.app,https://ca-traffic-git-main.vercel.app
```

### Frontend (Vercel)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_BACKEND_WS_URL` | **YES** | (none) | Full WebSocket URL to Railway backend, including `/ws` path. Must use `wss://` protocol. |

**Example:**
```
VITE_BACKEND_WS_URL=wss://ca-backend-production.railway.app/ws
```

---

## Updating Deployments

### Backend Updates (Railway)
Railway automatically redeploys when you push to the connected git branch:
```bash
git add backend/
git commit -m "Update backend"
git push
```

### Frontend Updates (Vercel)
Vercel automatically redeploys when you push to the connected git branch:
```bash
git add frontend/
git commit -m "Update frontend"
git push
```

Both platforms support zero-downtime deployments.

---

## Preview Deployments (Branch/PR Testing)

### Railway Preview Environments
1. Go to backend service → **Settings** → **Environments**
2. Enable **PR Deploys** to get a unique Railway URL per pull request

### Vercel Preview Deployments
- Vercel automatically creates preview deployments for every branch/PR
- Each gets a unique URL: `https://your-app-git-branch-name.vercel.app`
- Preview deployments use the same environment variables unless overridden

**For preview deployments to work with different backends:**
- Set `VITE_BACKEND_WS_URL` per environment in Vercel
- Or use Railway's preview URLs and update Vercel's preview env vars accordingly

---

## Troubleshooting

### Issue: "WebSocket connection failed" in browser console

**Possible Causes:**
1. ❌ `VITE_BACKEND_WS_URL` not set in Vercel environment variables
2. ❌ Backend Railway URL is incorrect or not publicly accessible
3. ❌ Using `ws://` instead of `wss://` (must use secure WebSocket for HTTPS frontend)
4. ❌ Missing `/ws` path in URL

**Solution:**
- Check Vercel → Project Settings → Environment Variables → `VITE_BACKEND_WS_URL`
- Should be: `wss://<railway-domain>/ws`
- Redeploy frontend after fixing: Vercel dashboard → Deployments → ⋯ → Redeploy

### Issue: "CORS policy" error in browser console

**Cause:** Backend `ALLOWED_ORIGINS` doesn't include the Vercel domain.

**Solution:**
1. Go to Railway backend service → Variables
2. Set `ALLOWED_ORIGINS=https://your-app.vercel.app,https://*.vercel.app`
3. Redeploy backend if needed

### Issue: "Application failed to respond" on Railway

**Cause:** Backend not listening on Railway's `$PORT`.

**Solution:**
- Verify `backend/Dockerfile` CMD uses: `CA_PORT=${PORT:-8000}`
- Check backend logs in Railway dashboard for port binding errors

### Issue: Frontend 404 on page refresh (client-side routes)

**Cause:** Missing SPA fallback configuration.

**Solution:**
- Ensure `frontend/vercel.json` exists with proper rewrites (already included in this repo)
- Redeploy frontend

### Issue: Environment variable not taking effect

**Cause:** Stale build cache or forgot to redeploy.

**Solution:**
- Vercel: Go to Deployments → Latest deployment → ⋯ → Redeploy
- Railway: Settings → Service → Restart
- **Remember:** Vite env vars are **build-time**, not runtime. Changing `VITE_BACKEND_WS_URL` requires a **new build**.

---

## Architecture Diagram

```
┌───────────────────────────────────────────────────────────┐
│  User's Browser                                           │
│  https://your-app.vercel.app                              │
└─────────────┬─────────────────────────────────────────────┘
              │
              │ HTTPS (static assets)
              ▼
┌───────────────────────────────────────────────────────────┐
│  Vercel CDN                                               │
│  Serves: React + PixiJS static build                      │
│  (frontend/ directory)                                    │
└───────────────────────────────────────────────────────────┘
              │
              │ WSS (WebSocket Secure)
              │ wss://backend.railway.app/ws
              ▼
┌───────────────────────────────────────────────────────────┐
│  Railway Container                                        │
│  Runs: FastAPI + WebSocket server (backend/ directory)   │
│  Listens on: $PORT (Railway-injected)                    │
│  CORS: Allows Vercel domain                              │
└───────────────────────────────────────────────────────────┘
```

---

## Local Development vs Production

### Local Development (Docker Compose)
- Uses `docker-compose.yml` (for reference)
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173` with Vite proxy to backend
- Same-origin WebSocket connection

### Production (Railway + Vercel)
- Backend: Railway container with dynamic `$PORT`
- Frontend: Vercel static hosting
- Cross-origin WebSocket connection via `VITE_BACKEND_WS_URL`
- CORS explicitly configured

---

## Security Recommendations

1. **Lock Down CORS**: Set `ALLOWED_ORIGINS` to specific Vercel domains, not `*`
2. **Use Environment Variables**: Never commit production URLs or secrets to git
3. **Enable HTTPS**: Both Railway and Vercel enforce HTTPS by default
4. **Rate Limiting**: Consider adding rate limiting to backend endpoints in production
5. **WebSocket Authentication**: For private deployments, add authentication to `/ws` endpoint

---

## Cost Estimates

### Railway (Backend)
- **Hobby Plan**: $5/month + usage-based pricing
- Typical backend usage: ~$5-10/month for moderate traffic

### Vercel (Frontend)
- **Hobby Plan**: Free for personal projects
- **Pro Plan**: $20/month for commercial use
- Bandwidth: 100GB/month free (Hobby), then usage-based

---

## Support & Resources

- **Railway Docs**: [docs.railway.app](https://docs.railway.app/)
- **Vercel Docs**: [vercel.com/docs](https://vercel.com/docs)
- **Vite Environment Variables**: [vitejs.dev/guide/env-and-mode](https://vitejs.dev/guide/env-and-mode)
- **FastAPI CORS**: [fastapi.tiangolo.com/tutorial/cors](https://fastapi.tiangolo.com/tutorial/cors/)

---

## License

MIT
