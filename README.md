<div align="center">

# sadak — CA Rule 184 Traffic Simulator & OpenStreetMap Importer

### Real-Time Cellular Automata Traffic Simulator with OpenStreetMap Region Import & Docker Deployment

[![Docker](https://img.shields.io/badge/docker-ready-blue?logo=docker&logoColor=white)](#quick-start-with-docker)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18%2B-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![PixiJS](https://img.shields.io/badge/PixiJS-8%2B-e91e63?logo=pixijs&logoColor=white)](https://pixijs.com/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Quick Start with Docker](#quick-start-with-docker)
- [Repository Structure](#repository-structure)
- [Local Development Setup](#local-development-setup)
- [OpenStreetMap Region Import](#openstreetmap-region-import)
- [Testing & Verification](#testing--verification)
- [Deployment on Google Cloud VM](#deployment-on-google-cloud-vm)
- [License](#license)

---

## Overview

This repository contains a full-stack, real-time cellular automata traffic simulator based on **Rule 184** principles, extended to support complex 2D road networks, junctions, disruptions, and live OpenStreetMap region imports.

The system features:
- **FastAPI + WebSockets Backend**: Asynchronous simulation engine broadcasting real-time traffic states and analytics (density, flow, entropy, landscape dynamics).
- **React + PixiJS Frontend**: High-performance 60 FPS GPU-accelerated canvas renderer with interactive map editor, region search, disruptions controls, and viewport controls.
- **OpenStreetMap Import**: Geocoding and Overpass API integration to import real-world campus/city street networks.
- **Docker Compose Setup**: Single-command containerized deployment for local development and cloud VMs (GCP, AWS).

---

## Key Features

- **Rule 184 Multi-Vehicle Simulation**: Simulates motorcycles, cars, buses, and trucks with distinct cell footprints and speeds.
- **OpenStreetMap Import**: Search any place (e.g. *"IIT BHU Varanasi"*, *"IIEST Shibpur"*) to fetch real road geometries and convert them to simulation networks.
- **Dynamic Disruptions**: Trigger vehicle breakdowns, fallen trees, accidents, or waterlogging in real time to observe congestion propagation.
- **Real-Time Analytics**: Live computation of spatial traffic density, flow rates, Shannon entropy, and thermodynamic landscape classification.
- **Containerized Deployment**: One-command launch using `docker compose up --build`.

### Deferred

Two visual features are specified but not built, both blocked on the same
gap rather than on rendering work:

- **Buildings, parking bays and handicap zones.** The Overpass query fetches
  only `highway=*` ways, so no area geometry reaches the frontend at all.
  Drawing them needs a backend feature first: fetching `building=*` and
  `amenity=parking` polygons, a model for areas, and a schema to carry them.
  The palette already reserves colours for all three.
- **Parking dynamics** (a vehicle that drives to a bay and stops). Depends on
  the bays above existing as real cells before a vehicle can occupy one.

---

## Quick Start with Docker

Run the entire application (Backend + Frontend) with a single command:

```bash
docker compose up -d --build
```

Access the application in your browser:
- **Frontend SPA:** [http://localhost](http://localhost)
- **Backend Health:** [http://localhost/health](http://localhost/health)

To stop services:
```bash
docker compose down
```

For detailed deployment instructions (including Google Cloud Platform Compute Engine VMs), see [**`DOCKER.md`**](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/DOCKER.md).

---

## Repository Structure

```text
ca-seepage-sim/
├── Dockerfile                  # Unified single-container build
├── docker-compose.yml          # Multi-container orchestration (backend + frontend)
├── DOCKER.md                   # Docker & Google Cloud VM deployment guide
├── SETUP.md                    # Manual local development setup guide
├── PHASE_REPORT.md             # Stage-by-stage implementation and verification report
├── pyproject.toml              # Pytest configuration
├── backend/                    # Python FastAPI + WebSocket Backend
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── run_server.py       # Main backend entry point
│   │   └── ws_smoke_client.py  # WebSocket integration client
│   ├── src/
│   │   ├── analytics/          # Density, entropy, and heatmap computation
│   │   ├── core/               # Rule 184 engine, cell grid, disruptions
│   │   ├── engine/             # Simulation manager & tick loop
│   │   ├── mapdata/            # OpenStreetMap geocoding & Overpass API client
│   │   ├── network/            # Road network topology & landscape classifier
│   │   └── server/             # FastAPI app & WebSocket endpoints
│   └── tests/                  # Pytest unit & integration test suite
├── frontend/                   # React + PixiJS + Vite Frontend
│   ├── Dockerfile
│   ├── nginx.conf              # Nginx reverse proxy configuration
│   ├── package.json
│   ├── src/
│   │   ├── components/         # Canvas, ControlPanel, RegionSearch, MapEditor
│   │   ├── render/             # PixiJS RoadRenderer canvas engine
│   │   ├── hooks/              # useSimulationSocket hook
│   │   └── App.tsx
│   └── vite.config.ts
├── docs/                       # Architecture diagrams & stage evidence
└── scripts/                    # Regression & smoke test scripts
```

---

## Local Development Setup

### Backend (Python)

```bash
# 1. Activate virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Start backend server
python backend/scripts/run_server.py
```
*Backend runs on `http://127.0.0.1:8000`.*

### Frontend (React + Vite)

```bash
# 1. Navigate to frontend
cd frontend

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
```
*Frontend dev server runs on `http://localhost:5173`.*

See [**`SETUP.md`**](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/SETUP.md) for full manual setup instructions.

---

## OpenStreetMap Region Import

You can import real road networks directly from OpenStreetMap:

1. Open the simulator UI in your browser.
2. Locate the **Import Region** panel in the right sidebar.
3. Type a campus or location name (e.g., *"IIT BHU Varanasi"* or *"Connaught Place, New Delhi"*).
4. Click **Import**. The backend fetches bounding coordinates via Nominatim, retrieves road ways from the Overpass API, builds a connected road network, and streams it to the canvas.

---

## Testing & Verification

Run the Python backend test suite:

```bash
.venv/bin/pytest backend/tests
```

Run frontend typechecking and build validation:

```bash
npm --prefix frontend run build
```

---

## Deployment on Google Cloud VM

To deploy on a GCP Compute Engine VM:

```bash
# SSH into your VM and run:
git clone <YOUR_GIT_REPO_URL>
cd ca-seepage-sim

# Launch with Docker Compose
docker compose up -d --build
```
Navigate to `http://<YOUR_VM_EXTERNAL_IP>` in your browser.

---

## License

This project is licensed under the MIT License.