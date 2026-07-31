"""
state_serializer.py — convert the NumPy `Simulation` state into compact,
frontend-friendly JSON messages.

Message schema (v1, Stage 2)
============================
Two server → client message kinds. Structure that rarely changes is sent
separately from per-tick occupancy so the per-tick payload stays small and
every later stage extends this same schema rather than replacing it.

1. "network" — sent once on connect and whenever the network *structure*
   changes (Stage 6 map edits). Describes roads' fixed geometry.

   {
     "type": "network",
     "roads": [
       {"id": 0, "length": 500,
        "geometry": {"x0": 0.0, "y0": 0.0, "dx": 1.0, "dy": 0.0},
        "periodic": true}
     ],
     "junctions": []            # Stage 3
   }

2. "state" — sent every tick. Carries only what changes.

   {
     "type": "state",
     "step": 1234,              # monotonic; client rejects stale/out-of-order
     "running": true,
     "steps_per_second": 12.0,
     "roads": [
       {"id": 0, "cells": [0,1,0,...]}   # 0=empty, 1=vehicle (Stage 2)
     ],
     "disruptions": [],         # Stage 4
     "analytics": {             # Stage 5 extends with entropy, per-segment
       "density": 0.42,
       "flow": 0.35
     }
   }

Client → server control messages are documented in ws_server.py.
"""

from __future__ import annotations

from typing import Any

from src.engine.simulation import Simulation


def serialize_network(sim: Simulation) -> dict[str, Any]:
    """Structural message: fixed geometry, sent on connect / structure change."""
    return {
        "type": "network",
        "roads": [
            {
                "id": r.id,
                "length": r.length,
                "geometry": r.geometry(),
                "periodic": r.periodic,
            }
            for r in sim.roads
        ],
        "junctions": [],  # populated in Stage 3
    }


def serialize_state(sim: Simulation) -> dict[str, Any]:
    """Per-tick message: occupancy + live analytics, stamped with `step`."""
    return {
        "type": "state",
        "step": sim.step_count,
        "running": sim.running,
        "steps_per_second": sim.steps_per_second,
        "roads": [
            {
                "id": r.id,
                # tolist() keeps the JSON small and avoids NumPy int types
                "cells": r.cells.astype(int).tolist(),
            }
            for r in sim.roads
        ],
        "disruptions": [],  # populated in Stage 4
        "analytics": {
            "density": round(sim.density(), 6),
            "flow": round(sim.flow(), 6),
        },
    }
