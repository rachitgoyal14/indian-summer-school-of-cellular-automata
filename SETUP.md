# Setup Guide

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- **Docker & Docker Compose** (optional, for 1-command deployment)

---

## ⚡ Quick Start with Docker (Recommended)

Run the entire application (Backend + Frontend) with a single command:

```bash
docker compose up --build
```

Access the app at **http://localhost** in your browser.
See [DOCKER.md](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/DOCKER.md) for full Docker and Google Cloud VM deployment details.

---

## Backend

The backend is a FastAPI + WebSocket server (powered by Uvicorn) that streams the Rule 184 simulation.

```bash
# 1. Create & activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Start the server
python backend/scripts/run_server.py
```

The server starts on **http://127.0.0.1:8000** by default.

| Endpoint | URL |
|---|---|
| WebSocket | `ws://localhost:8000/ws` |
| Health check | `http://localhost:8000/health` |

**Environment variables** (optional):

| Variable | Default | Description |
|---|---|---|
| `CA_HOST` | `127.0.0.1` | Host to bind to |
| `CA_PORT` | `8000` | Port to listen on |

**Alternative** — run directly with Uvicorn:

```bash
uvicorn src.server.ws_server:app --app-dir backend --reload --port 8000
```

---

## Frontend

The frontend is a React + PixiJS app built with Vite and TypeScript.

```bash
# 1. Install dependencies (from frontend/)
cd frontend
npm install

# 2. Start the dev server
npm run dev
```

The dev server starts on **http://localhost:5173** and automatically proxies WebSocket requests (`/ws`) to the backend at `ws://127.0.0.1:8000`.

**Other commands:**

| Command | Description |
|---|---|
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview the production build |
| `npm run typecheck` | Run TypeScript type checking only |

---

## Running Both Together

Open **two terminals** from the project root directory:

```bash
# Terminal 1 — Backend
source .venv/bin/activate
python backend/scripts/run_server.py

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Then open **http://localhost:5173** in your browser.
