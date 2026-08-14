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
from src.analytics.heatmap import segment_densities


def serialize_streets(sim: Simulation) -> list[dict[str, Any]]:
    """
    The lane groupings, so the renderer can draw one road surface per street
    with lane markings on it instead of inferring adjacency from N nearly
    overlapping road lines.

    Empty for a single-lane network — a client that ignores this key still
    renders every lane as its own road, which is what it did before.
    """
    streets = []
    for street in sim.network.streets_ordered():
        streets.append({
            "id": street.id,
            "baseline": street.baseline_geometry(),
            "lane_width": street.lane_width,
            "n_forward": len(street.lanes_in_direction("forward")),
            "n_backward": len(street.lanes_in_direction("backward")),
            "lanes": [
                {
                    "road_id": lane.road.id,
                    "lane_index": lane.lane_index,
                    "direction": lane.direction,
                    "left_road_id": (lane.left_lane.road.id
                                     if lane.left_lane else None),
                    "right_road_id": (lane.right_lane.road.id
                                      if lane.right_lane else None),
                }
                for lane in street.all_lanes()
            ],
        })
    return streets


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
                # which street this lane belongs to, if any (null = plain road)
                "street_id": r.street_id,
                "lane_index": r.lane_index,
            }
            for r in sim.roads
        ],
        "junctions": [
            {"id": j.id, "x": j.x, "y": j.y}
            for j in sim.network.junctions.values()
        ],
        "streets": serialize_streets(sim),
    }


def serialize_state(sim: Simulation) -> dict[str, Any]:
    queues = sim.junction_queue_lengths()
    entropy_bits, entropy_norm = sim.entropy()
    return {
        "type": "state",
        "step": sim.step_count,
        "running": sim.running,
        "steps_per_second": sim.steps_per_second,
        # "live" while the tick loop is streaming; a batch result is labelled
        # "batch" at its own top level, so the UI can tell the two apart.
        "mode": sim.mode,
        "lane_change_prob": sim.lane_change_prob,
        "rear_safety_gap": sim.rear_safety_gap,
        "lane_change_require_gain": sim.lane_change_require_gain,
        # lateral transfers on this step; also mirrored inside "analytics"
        "lane_changes": sim.lane_changes(),
        "roads": [
            {
                "id": r.id,
                "cells": r.cells.astype(int).tolist(),
                "vehicles": [
                    {"f": v.front, "l": v.length, "t": v.vtype}
                    for v in r.vehicles
                ],
                # per-segment congestion for the heatmap overlay (Stage 5)
                "segments": segment_densities(r.cells),
            }
            for r in sim.roads
        ],
        "junctions": [
            {"id": jid, "queue": q} for jid, q in queues.items()
        ],
        "disruptions": sim.disruptions.to_list(),
        "analytics": {
            "density": round(sim.density(), 6),
            "flow": round(sim.flow(), 6),
            "entropy": round(entropy_norm, 6),      # normalised 0..1 (UI-friendly)
            "entropy_bits": round(entropy_bits, 6),
            "blocked_fraction": round(sim.blocked_fraction(), 6),
            "avg_queue": round(sim.avg_queue_length(), 4),
            "lane_changes": sim.lane_changes(),      # lateral moves last step
            "landscape": sim.landscape(),           # trivial | average | worst
        },
    }
