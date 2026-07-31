"""
state_serializer.py — convert the NumPy `Simulation`/`Network` state into
compact, frontend-friendly JSON messages.

Message schema
==============
Two server → client message kinds; structure is sent separately from
per-tick occupancy so the per-tick payload stays small.

1. "network" (on connect / structure change):
   {
     "type": "network",
     "config": "grid",
     "roads": [{"id", "length", "geometry":{x0,y0,dx,dy}, "periodic"}],
     "junctions": [{"id", "x", "y"}]
   }

2. "state" (every tick):
   {
     "type": "state",
     "step", "running", "steps_per_second",
     "roads": [{
        "id",
        "cells": [0/1 ...],                     # occupancy (compat + heatmap)
        "vehicles": [{"f": front, "l": length, "t": "moto"|"car"}]
     }],
     "junctions": [{"id", "queue"}],            # per-junction backup length
     "disruptions": [],                          # Stage 4
     "analytics": {"density", "flow"}            # Stage 5 extends
   }

`cells` (occupancy) and `vehicles` are both sent: `vehicles` drives
footprint-accurate rendering; `cells` supports the desync check, density,
and the Stage 5 heatmap.
"""

from __future__ import annotations

from typing import Any

from src.engine.simulation import Simulation


def serialize_network(sim: Simulation) -> dict[str, Any]:
    return {
        "type": "network",
        "config": sim.config,
        "roads": [
            {
                "id": r.id,
                "length": r.length,
                "geometry": r.geometry(),
                "periodic": r.periodic,
            }
            for r in sim.roads
        ],
        "junctions": [
            {"id": j.id, "x": j.x, "y": j.y}
            for j in sim.network.junctions.values()
        ],
    }


def serialize_state(sim: Simulation) -> dict[str, Any]:
    queues = sim.junction_queue_lengths()
    return {
        "type": "state",
        "step": sim.step_count,
        "running": sim.running,
        "steps_per_second": sim.steps_per_second,
        "roads": [
            {
                "id": r.id,
                "cells": r.cells.astype(int).tolist(),
                "vehicles": [
                    {"f": v.front, "l": v.length, "t": v.vtype}
                    for v in r.vehicles
                ],
            }
            for r in sim.roads
        ],
        "junctions": [
            {"id": jid, "queue": q} for jid, q in queues.items()
        ],
        "disruptions": [],  # populated in Stage 4
        "analytics": {
            "density": round(sim.density(), 6),
            "flow": round(sim.flow(), 6),
        },
    }
