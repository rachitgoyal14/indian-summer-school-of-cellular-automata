"""
run_server.py — main backend entry point.

Starts the FastAPI + WebSocket server that streams the Rule 184 simulation
to the browser frontend.

Usage
-----
    # from project root  (with the venv active)
    python backend/scripts/run_server.py
    # or, equivalently:
    uvicorn src.server.ws_server:app --app-dir backend --reload --port 8000

The WebSocket endpoint is  ws://localhost:8000/ws
A health check is at       http://localhost:8000/health
"""

from __future__ import annotations

import os
import sys

# Make `src.*` importable exactly like the tests do (backend/ is the root).
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import uvicorn  # noqa: E402


def main() -> None:
    host = os.environ.get("CA_HOST", "0.0.0.0")
    port = int(os.environ.get("CA_PORT", "8000"))
    uvicorn.run("src.server.ws_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
