# Docker Deployment & Local Setup Guide

This guide explains how to run the **CA Rule 184 Traffic Simulator** locally using Docker or deploy it to a Google Cloud Platform (GCP) Virtual Machine with a single command.

---

## Quick Start (Single Command)

To run the entire application (Frontend + Backend) with Docker Compose:

```bash
docker compose up --build
```

Once running, access the application in your browser at:
- **Frontend App:** [http://localhost](http://localhost) (or `http://<YOUR_VM_PUBLIC_IP>`)
- **Backend Health Check:** [http://localhost/health](http://localhost/health)

To run in detached mode (in background):
```bash
docker compose up -d --build
```

To stop all services:
```bash
docker compose down
```

---

## Architecture Overview

The Docker Compose setup launches two orchestrated containers:

1. **`ca-backend` (FastAPI + WebSockets)**
   - Listens on `0.0.0.0:8000` inside container.
   - Executes Rule 184 cellular automata traffic simulation tick loop.
   - Healthcheck endpoint at `/health`.

2. **`ca-frontend` (Nginx + React/PixiJS SPA)**
   - Serves static compiled bundle on port `80`.
   - Proxies WebSocket requests (`/ws`) and health requests (`/health`) to `http://backend:8000`.

---

## Deploying to a Google Cloud Platform (GCP) VM

### Step 1: Create a GCP Compute Engine VM Instance

Using `gcloud` CLI or Google Cloud Console:
- **OS:** Ubuntu 22.04 LTS or Debian 12
- **Machine Type:** `e2-small` or `e2-medium`
- **Firewall:** Check **Allow HTTP traffic** (Port 80) and **Allow HTTPS traffic** (Port 443).

*Example gcloud command:*
```bash
gcloud compute instances create ca-traffic-sim-vm \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=http-server,https-server
```

---

### Step 2: Install Docker & Docker Compose on the GCP VM

SSH into your GCP VM instance and run:

```bash
# 1. Update system package index
sudo apt update && sudo apt upgrade -y

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. Allow your user to run docker without sudo
sudo usermod -aG docker $USER
newgrp docker

# 4. Verify installation
docker compose version
```

---

### Step 3: Clone Code & Start Application

```bash
# Clone your repository
git clone <YOUR_GIT_REPO_URL>
cd ca-seepage-sim

# Launch services in detached mode
docker compose up -d --build
```

---

### Step 4: Access Your Application

Open your browser and navigate to:
```text
http://<YOUR_GCP_VM_EXTERNAL_IP>
```

*(Make sure GCP Firewall rules allow incoming traffic on Port 80 for tag `http-server`).*

To check container logs on VM:
```bash
docker compose logs -f
```

---

## Alternative: Single Container Build

If you prefer building a unified single container (e.g. for Google Cloud Run or App Engine):

```bash
# Build single container
docker build -t ca-simulator .

# Run single container
docker run -d -p 80:80 --name ca-app ca-simulator
```
