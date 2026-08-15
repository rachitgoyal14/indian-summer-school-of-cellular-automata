"""
scenario_io.py — save/load a full simulation scenario to/from JSON (Stage 6).

A scenario captures everything needed to reproduce the current state exactly:
network structure (roads + junctions + turns), every vehicle, the disruption
settings and every active disruption, and the top-level simulation parameters.

`save_scenario(sim) → dict` and `network_from_scenario(dict) → Network` are the
core; `Simulation.apply_scenario` (engine) uses them to load in place. The
round-trip is exact: save → load → save yields an identical dict (tested).
"""

from __future__ import annotations

from typing import Any

from src.core.vehicle import Vehicle
from src.core.junction import Junction
from src.core.disruptions import Disruption
from src.network.network import Network, Road
from src.network.street import Lane, Street

SCENARIO_VERSION = 1


def save_scenario(sim) -> dict[str, Any]:
    """Serialize a Simulation into a JSON-safe scenario dict."""
    net: Network = sim.network
    roads = []
    for r in net.roads_ordered():
        roads.append({
            "id": r.id,
            "length": r.length,
            "x0": r.x0, "y0": r.y0, "dx": r.dx, "dy": r.dy,
            "periodic": r.periodic,
            "head_junction": r.head_junction,
            "tail_junction": r.tail_junction,
            "source_rate": r.source_rate,
            "source_car_fraction": r.source_car_fraction,
            "street_id": r.street_id,
            "lane_index": r.lane_index,
            "name": r.name,
            "path": [[round(x, 3), round(y, 3)] for x, y in r.path],
            "vehicles": [
                {"id": v.id, "front": v.front, "length": v.length, "vtype": v.vtype}
                for v in sorted(r.vehicles, key=lambda v: v.front)
            ],
        })
    junctions = []
    for j in sorted(net.junctions.values(), key=lambda j: j.id):
        # JSON object keys must be strings
        turns = {
            str(in_road): {str(out): p for out, p in outs.items()}
            for in_road, outs in j.turns.items()
        }
        lane_links = {
            str(in_road): sorted(outs) for in_road, outs in j.lane_links.items()
        }
        junctions.append({"id": j.id, "x": j.x, "y": j.y, "turns": turns,
                          "lane_links": lane_links})
    # Stage 9 lane groups. `street_id` / `lane_index` already ride along on each
    # road; this records the part a road cannot carry — the lane's direction and
    # the grouping itself — so the registry survives the round-trip.
    streets = [
        {
            "id": s.id,
            "baseline": list(s.baseline) if s.baseline is not None else None,
            "centerline_path": [[x, y] for x, y in s.centerline_path],
            "lane_width": s.lane_width,
            "lanes": [
                {"road_id": lane.road.id, "lane_index": lane.lane_index,
                 "direction": lane.direction}
                for lane in s.all_lanes()
            ],
        }
        for s in net.streets_ordered()
    ]

    return {
        "version": SCENARIO_VERSION,
        "config": sim.config,
        "step": sim.step_count,
        "seed": sim.seed,
        # RNG state so a loaded sim continues the *exact* stochastic stream
        "rng_state": sim._rng.bit_generator.state,
        "density_target": sim.density_target,
        "car_fraction": sim.car_fraction,
        # every lateral-transfer knob, always written explicitly: each one
        # changes the outcome of a step, so a scenario that omitted any of
        # them would not reproduce exactly.
        "lane_change_prob": sim.lane_change_prob,
        "rear_safety_gap": sim.rear_safety_gap,
        "lane_change_require_gain": sim.lane_change_require_gain,
        "steps_per_second": sim.steps_per_second,
        "roads": roads,
        "junctions": junctions,
        "streets": streets,
        "disruptions": {
            "probs": dict(sim.disruptions.probs),
            "repair_scale": sim.disruptions.repair_scale,
            "active": sim.disruptions.to_list(),
        },
    }


def network_from_scenario(data: dict[str, Any]) -> Network:
    """Rebuild a Network (structure + vehicles) from a scenario dict."""
    net = Network()
    # pre-Stage-9 scenarios carry none of these; the defaults are the old
    # behaviour (no lateral pass at all), so those files load unchanged.
    net.lane_change_prob = float(data.get("lane_change_prob", 0.0))
    net.rear_safety_gap = int(data.get("rear_safety_gap", 0))
    net.lane_change_require_gain = bool(data.get("lane_change_require_gain", True))
    max_vid = 0
    for rd in data["roads"]:
        road = Road(
            id=int(rd["id"]), length=int(rd["length"]),
            x0=rd["x0"], y0=rd["y0"], dx=rd["dx"], dy=rd["dy"],
            periodic=bool(rd["periodic"]),
            head_junction=rd["head_junction"], tail_junction=rd["tail_junction"],
            source_rate=rd.get("source_rate", 0.0),
            source_car_fraction=rd.get("source_car_fraction", 0.0),
            street_id=rd.get("street_id"),
            lane_index=int(rd.get("lane_index", 0)),
            name=rd.get("name", ""),
            path=[(float(x), float(y)) for x, y in rd.get("path", [])],
        )
        for vd in rd["vehicles"]:
            road.vehicles.append(
                Vehicle(int(vd["id"]), int(vd["front"]), int(vd["length"]), vd["vtype"])
            )
            max_vid = max(max_vid, int(vd["id"]))
        net.add_road(road)
    for jd in data["junctions"]:
        turns = {
            int(in_road): {int(out): float(p) for out, p in outs.items()}
            for in_road, outs in jd["turns"].items()
        }
        lane_links = {
            int(in_road): [int(o) for o in outs]
            for in_road, outs in (jd.get("lane_links") or {}).items()
        }
        net.add_junction(Junction(id=int(jd["id"]), x=jd["x"], y=jd["y"],
                                  turns=turns, lane_links=lane_links))
    # `streets` is absent from pre-Stage-9 scenarios; those load as before.
    for sd in data.get("streets", []):
        baseline = sd.get("baseline")
        street = Street(
            str(sd["id"]),
            baseline=tuple(baseline) if baseline else None,
            lane_width=float(sd.get("lane_width", 0.0)),
            # Absent from scenarios saved before the renderer needed the
            # un-offset curve; those load with an empty path and fall back to
            # `baseline`, exactly as they did.
            centerline_path=[
                (float(x), float(y)) for x, y in sd.get("centerline_path", [])
            ],
        )
        for ld in sd["lanes"]:
            street.add_lane(Lane(
                road=net.roads[int(ld["road_id"])],
                lane_index=int(ld["lane_index"]),
                direction=ld["direction"],
            ))
        net.add_street(street)
    net._vid = max_vid
    net.validate()
    return net


def restore_disruptions(sim, data: dict[str, Any]) -> None:
    """Restore disruption settings + active instances onto sim.disruptions."""
    dd = data.get("disruptions", {})
    sim._disruption_probs = dict(dd.get("probs", {}))
    sim._repair_scale = float(dd.get("repair_scale", 1.0))
    sim._apply_disruption_settings()
    active = []
    max_id = 0
    for a in dd.get("active", []):
        active.append(Disruption(
            id=int(a["id"]), kind=a["kind"], label=a["label"],
            road_id=int(a["road_id"]), cells=[int(c) for c in a["cells"]],
            permanent=bool(a["permanent"]), remaining=int(a.get("remaining", 0)),
        ))
        max_id = max(max_id, int(a["id"]))
    sim.disruptions.active = active
    sim.disruptions.next_id = max_id + 1
    sim.disruptions._publish()
