"""
scenario_runner.py — batch ("what-if") scenario execution (Stage 10).

Live mode steps a shared `Simulation` and broadcasts a state message every
tick. Batch mode does the opposite: it builds its *own* `Simulation`, runs it
for a fixed number of steps with nothing streamed anywhere, and returns one
result object with the whole analytics trajectory.

Isolation
---------
A batch run never touches the live simulation. The input is plain JSON data —
either a saved scenario dict or a small hand-written config — and the runner
constructs a fresh `Simulation` from it. To branch off the live world the
caller passes `sim.to_scenario()`, which is already a deep, pure-data copy
including the RNG state, so there is no object sharing to get wrong. The live
simulation's RNG, vehicles and analytics are untouched by construction.

Determinism
-----------
Stepping goes through `Simulation.advance(1)` — the exact call the live tick
loop makes — so a batch run of N steps is bit-for-bit the same world as N live
steps from the same config. Scheduled events fire at a fixed point in the
order (before the step they name), so event-driven runs are reproducible too.

Input format
------------
A strict superset of `save_scenario`'s output, so any saved scenario is a
valid batch input. Two ways to specify the world:

  full      the scenario dict itself (has a "roads" key) — loaded verbatim
            through `Simulation.apply_scenario`, vehicles, RNG state and all.
  config    a short hand-written dict naming a builder:
              {"config": "grid", "seed": 7, "density": 0.3,
               "car_fraction": 0.3, "build_kwargs": {"rows": 3, "cols": 3}}

Batch-only settings live under a "batch" key:

  {"batch": {
      "steps": 500,             # required, 1 .. MAX_STEPS
      "record_every": 1,        # scalar analytics sampling stride
      "snapshot_every": 0,      # vehicle snapshots; 0 = first/middle/final only
      "include_segments": true, # per-road segment densities on snapshot steps
      "schedule": [ ... ]       # optional timed events, see SCHEDULE_ACTIONS
   }}

`seed` is mandatory: without it the same scenario would not reproduce. A full
scenario dict carries one already.

Result size
-----------
Scalar analytics are recorded every `record_every` steps and are tiny (a
handful of floats). The heavy data — per-road segment densities and full
vehicle positions — is recorded only on *snapshot* steps, which default to
just the first, middle and final step. That keeps a 10,000-step run on a large
network to a few MB in one WebSocket message, with no chunking protocol. A
run whose requested sampling would exceed `MAX_RECORDS` is rejected up front
with a clear error rather than being allowed to exhaust memory.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from src.analytics.entropy import network_entropy
from src.analytics.heatmap import segment_densities
from src.core.disruptions import ALL_KINDS, STOCHASTIC_SPECS, Disruption
from src.engine.simulation import Simulation
from src.network.landscape import classify_landscape

#: hard ceilings, so a malformed request fails loudly instead of OOMing
MAX_STEPS = 100_000
MAX_RECORDS = 100_000
MAX_SNAPSHOTS = 2_000

#: scheduled-event actions and their required fields
SCHEDULE_ACTIONS = {
    "trigger_disruption": ("kind",),
    "clear_disruptions": (),
    "block_cells": ("road_id", "cells"),
    "set_disruption_params": (),
    "set_source_rate": ("road_id", "value"),
    "set_lane_change_params": (),
}


class ScenarioError(ValueError):
    """
    An invalid scenario specification. Carries a client-safe message.

    `code` is a stable machine-readable tag the frontend can branch on without
    parsing prose: `INVALID_CONFIG` for anything malformed, `OVERSIZED_REQUEST`
    when the run would exceed the result ceilings. The server adds
    `ALREADY_RUNNING` when a batch is in flight.
    """

    def __init__(self, message: str, code: str = "INVALID_CONFIG") -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------- spec
def _require_int(data: dict, key: str, lo: int, hi: int, default: Any = None) -> int:
    raw = data.get(key, default)
    if raw is None:
        raise ScenarioError(f"'{key}' is required")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ScenarioError(f"'{key}' must be an integer, got {raw!r}") from None
    if not lo <= value <= hi:
        raise ScenarioError(f"'{key}' must be between {lo} and {hi}, got {value}")
    return value


def _require_float(data: dict, key: str, lo: float, hi: float, default: Any) -> float:
    raw = data.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ScenarioError(f"'{key}' must be a number, got {raw!r}") from None
    if not lo <= value <= hi:
        raise ScenarioError(f"'{key}' must be between {lo} and {hi}, got {value}")
    return value


def validate(spec: dict[str, Any]) -> dict[str, Any]:
    """
    Check a scenario spec and return its normalised "batch" settings.

    Raises `ScenarioError` with a message meant for the client. Everything that
    can be checked without building the world is checked here, so a bad request
    never gets far enough to disturb anything.
    """
    if not isinstance(spec, dict):
        raise ScenarioError("scenario must be a JSON object")

    batch = spec.get("batch") or {}
    if not isinstance(batch, dict):
        raise ScenarioError("'batch' must be a JSON object")

    steps = _require_int(batch, "steps", 1, MAX_STEPS)
    record_every = _require_int(batch, "record_every", 1, MAX_STEPS, 1)
    snapshot_every = _require_int(batch, "snapshot_every", 0, MAX_STEPS, 0)

    if steps // record_every + 1 > MAX_RECORDS:
        raise ScenarioError(
            f"trajectory would hold more than {MAX_RECORDS} records; "
            f"raise 'record_every'",
            code="OVERSIZED_REQUEST",
        )
    if snapshot_every and steps // snapshot_every + 1 > MAX_SNAPSHOTS:
        raise ScenarioError(
            f"run would hold more than {MAX_SNAPSHOTS} vehicle snapshots; "
            f"raise 'snapshot_every' or set it to 0",
            code="OVERSIZED_REQUEST",
        )

    if spec.get("seed") is None:
        raise ScenarioError("'seed' is required so the run is reproducible")
    _require_int(spec, "seed", -(2 ** 63), 2 ** 63 - 1)

    if "roads" not in spec:
        # a hand-written config: validate what the constructor will be given
        _require_float(spec, "density", 0.0, 1.0, spec.get("density_target", 0.3))
        _require_float(spec, "car_fraction", 0.0, 1.0, 0.0)
        _require_float(spec, "lane_change_prob", 0.0, 1.0, 0.0)
        from src.network.grid_builder import BUILDERS

        config = spec.get("config", "one_way")
        if config not in BUILDERS:
            raise ScenarioError(
                f"unknown config {config!r}; choices: {sorted(BUILDERS)}"
            )

    schedule = batch.get("schedule") or []
    if not isinstance(schedule, list):
        raise ScenarioError("'batch.schedule' must be a list of events")
    for i, event in enumerate(schedule):
        _validate_event(i, event, steps)

    return {
        "steps": steps,
        "record_every": record_every,
        "snapshot_every": snapshot_every,
        "include_segments": bool(batch.get("include_segments", True)),
        "schedule": schedule,
    }


def _validate_event(i: int, event: Any, steps: int) -> None:
    where = f"batch.schedule[{i}]"
    if not isinstance(event, dict):
        raise ScenarioError(f"{where} must be a JSON object")
    action = event.get("action")
    if action not in SCHEDULE_ACTIONS:
        raise ScenarioError(
            f"{where}: unknown action {action!r}; "
            f"choices: {sorted(SCHEDULE_ACTIONS)}"
        )
    step = event.get("step")
    if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < steps:
        raise ScenarioError(
            f"{where}: 'step' must be an integer in [0, {steps}), got {step!r}"
        )
    for field in SCHEDULE_ACTIONS[action]:
        if event.get(field) is None:
            raise ScenarioError(f"{where}: action {action!r} requires '{field}'")
    kind = event.get("kind")
    if action == "trigger_disruption" and kind not in STOCHASTIC_SPECS:
        raise ScenarioError(
            f"{where}: unknown disruption kind {kind!r}; "
            f"choices: {sorted(STOCHASTIC_SPECS)}"
        )
    if action == "clear_disruptions" and kind is not None and kind not in ALL_KINDS:
        raise ScenarioError(f"{where}: unknown disruption kind {kind!r}")
    if action == "block_cells":
        cells = event.get("cells")
        if not isinstance(cells, list) or not cells or not all(
            isinstance(c, int) and not isinstance(c, bool) for c in cells
        ):
            raise ScenarioError(f"{where}: 'cells' must be a non-empty list of ints")


# ------------------------------------------------------------------ building
def build_simulation(spec: dict[str, Any]) -> Simulation:
    """
    Build a fresh, isolated `Simulation` from a spec.

    Uses the same entry points as live mode — `apply_scenario` for a full
    scenario, the constructor for a named config — so the batch world is
    indistinguishable from a live world loaded the same way.
    """
    if "roads" in spec:
        sim = Simulation()
        sim.apply_scenario(spec)
        return sim
    return Simulation(
        config=spec.get("config", "one_way"),
        length=int(spec.get("length", 500)),
        density=float(spec.get("density", spec.get("density_target", 0.3))),
        seed=int(spec["seed"]),
        car_fraction=float(spec.get("car_fraction", 0.0)),
        lane_change_prob=float(spec.get("lane_change_prob", 0.0)),
        rear_safety_gap=int(spec.get("rear_safety_gap", 0)),
        lane_change_require_gain=bool(spec.get("lane_change_require_gain", True)),
        build_kwargs=spec.get("build_kwargs") or {},
    )


# ------------------------------------------------------------------- events
def apply_event(sim: Simulation, event: dict[str, Any]) -> dict[str, Any]:
    """
    Apply one scheduled event. Returns a record of what fired, for the summary.

    Road ids are resolved against the *built* network, so an event naming a
    road that does not exist fails here with a clear message rather than
    silently doing nothing.
    """
    action = event["action"]
    record = {"step": event["step"], "action": action, "ok": True}

    if action == "trigger_disruption":
        record["kind"] = event["kind"]
        record["ok"] = sim.trigger_disruption(event["kind"])
    elif action == "clear_disruptions":
        record["kind"] = event.get("kind")
        sim.clear_disruptions(event.get("kind"))
    elif action == "block_cells":
        record.update(_block_cells(sim, event))
    elif action == "set_disruption_params":
        sim.set_disruption_params(
            probs=event.get("probs"), repair_scale=event.get("repair_scale")
        )
        record["probs"] = event.get("probs")
        record["repair_scale"] = event.get("repair_scale")
    elif action == "set_source_rate":
        road = _road(sim, event["road_id"], event)
        road.source_rate = float(max(0.0, min(1.0, float(event["value"]))))
        record["road_id"] = road.id
        record["value"] = road.source_rate
    elif action == "set_lane_change_params":
        sim.set_lane_change_params(
            prob=event.get("prob"),
            rear_gap=event.get("rear_gap"),
            require_gain=event.get("require_gain"),
        )
        record["prob"] = sim.lane_change_prob
        record["rear_gap"] = sim.rear_safety_gap
    return record


def _road(sim: Simulation, road_id: Any, event: dict[str, Any]):
    road = sim.network.roads.get(int(road_id))
    if road is None:
        raise ScenarioError(
            f"scheduled event at step {event['step']} names unknown road id "
            f"{road_id!r}; the network has {sorted(sim.network.roads)[:12]}..."
        )
    return road


def _block_cells(sim: Simulation, event: dict[str, Any]) -> dict[str, Any]:
    """Place an explicit blockage — the hand-editable 'flood at step 200'."""
    road = _road(sim, event["road_id"], event)
    cells = sorted({int(c) for c in event["cells"]})
    out_of_range = [c for c in cells if not 0 <= c < road.length]
    if out_of_range:
        raise ScenarioError(
            f"scheduled event at step {event['step']}: cells {out_of_range} are "
            f"outside road {road.id} (length {road.length})"
        )
    permanent = bool(event.get("permanent", False))
    kind = event.get("kind", "flood")
    manager = sim.disruptions
    manager.active.append(Disruption(
        id=manager._new_id(), kind=kind,
        label=str(event.get("label", f"scheduled {kind}")),
        road_id=road.id, cells=cells, permanent=permanent,
        remaining=0 if permanent else int(event.get("duration", 100)),
    ))
    manager._publish()
    return {"road_id": road.id, "cells": cells, "permanent": permanent}


# ---------------------------------------------------------------- analytics
def _record(sim: Simulation, step: int) -> dict[str, Any]:
    """
    One trajectory record. Occupancies are built once and reused for every
    metric — the live path recomputes them per call, which is fine per tick
    but would dominate a long batch run. The values are identical.
    """
    net = sim.network
    roads = net.roads_ordered()
    occs = [r.occupancy() for r in roads]
    total_cells = sum(r.length for r in roads)
    occupied = sum(int(o.sum()) for o in occs)

    density = (occupied / total_cells) if total_cells else 0.0
    flow = (sim._last_moved / total_cells) if total_cells else 0.0
    entropy_bits, entropy_norm = network_entropy(occs)
    n_blocked = sum(len(s) for s in net.blocked.values())
    blocked_fraction = (n_blocked / total_cells) if total_cells else 0.0
    queues = net.junction_queue_lengths()
    avg_queue = (sum(queues.values()) / len(queues)) if queues else 0.0

    return {
        "step": step,
        "density": round(density, 6),
        "flow": round(flow, 6),
        "entropy": round(entropy_norm, 6),
        "entropy_bits": round(entropy_bits, 6),
        "blocked_fraction": round(blocked_fraction, 6),
        "avg_queue": round(avg_queue, 4),
        "landscape": classify_landscape(density, blocked_fraction, avg_queue),
        "lane_changes": net.last_lane_changes,
        "spawned": net.last_spawned,
        "exited": net.last_exited,
        "vehicles": sum(len(r.vehicles) for r in roads),
    }


def _snapshot(sim: Simulation, step: int, include_segments: bool) -> dict[str, Any]:
    """Heavy per-road data for one step: vehicles, and optionally segments."""
    roads = []
    for r in sim.network.roads_ordered():
        entry: dict[str, Any] = {
            "id": r.id,
            "vehicles": [
                {"f": v.front, "l": v.length, "t": v.vtype}
                for v in sorted(r.vehicles, key=lambda v: v.front)
            ],
        }
        if include_segments:
            entry["segments"] = segment_densities(r.occupancy())
        roads.append(entry)
    return {"step": step, "roads": roads}


def _snapshot_steps(steps: int, snapshot_every: int) -> set[int]:
    """Which step numbers get a heavy snapshot. Default: first, middle, last."""
    if snapshot_every > 0:
        marks = set(range(0, steps + 1, snapshot_every))
        marks.add(steps)
        return marks
    return {0, steps // 2, steps}


def _summarise(
    trajectory: list[dict[str, Any]],
    events: list[dict[str, Any]],
    elapsed: float,
) -> dict[str, Any]:
    """Derived statistics over the whole run."""
    if not trajectory:
        return {}
    flows = [r["flow"] for r in trajectory]
    entropies = [r["entropy"] for r in trajectory]
    half = trajectory[len(trajectory) // 2:]
    return {
        "steps": trajectory[-1]["step"],
        "records": len(trajectory),
        "peak_flow": max(flows),
        "mean_flow": round(sum(flows) / len(flows), 6),
        # second half only: an estimate of the steady state, after transients
        "steady_state_flow": round(sum(r["flow"] for r in half) / len(half), 6),
        "min_entropy": min(entropies),
        "max_entropy": max(entropies),
        "final_density": trajectory[-1]["density"],
        "final_landscape": trajectory[-1]["landscape"],
        "peak_avg_queue": max(r["avg_queue"] for r in trajectory),
        "total_lane_changes": sum(r["lane_changes"] for r in trajectory),
        "total_spawned": sum(r["spawned"] for r in trajectory),
        "total_exited": sum(r["exited"] for r in trajectory),
        "events_fired": events,
        "elapsed_seconds": round(elapsed, 4),
    }


# ---------------------------------------------------------------------- run
def run_scenario(spec: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a batch scenario and return its result.

    Pure and self-contained: builds its own `Simulation`, touches nothing
    global, and returns plain JSON-safe data. Raises `ScenarioError` on an
    invalid spec, before any world is built.
    """
    batch = validate(spec)
    steps = batch["steps"]
    record_every = batch["record_every"]
    include_segments = batch["include_segments"]

    sim = build_simulation(spec)

    # events bucketed by the step they fire before; stable order within a step
    schedule: dict[int, list[dict[str, Any]]] = {}
    for event in batch["schedule"]:
        schedule.setdefault(int(event["step"]), []).append(event)

    snapshot_at = _snapshot_steps(steps, batch["snapshot_every"])
    trajectory: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    fired: list[dict[str, Any]] = []

    started = time.perf_counter()
    for i in range(steps + 1):
        for event in schedule.get(i, ()):
            fired.append(apply_event(sim, event))
        # every `record_every` steps, and always the final step
        if i % record_every == 0 or i == steps:
            if not trajectory or trajectory[-1]["step"] != i:
                trajectory.append(_record(sim, i))
        if i in snapshot_at:
            snapshots.append(_snapshot(sim, i, include_segments))
        if i < steps:
            sim.advance(1)
    elapsed = time.perf_counter() - started

    return {
        "trajectory": trajectory,
        "snapshots": snapshots,
        "summary": _summarise(trajectory, fired, elapsed),
        # same schema as a live scenario, so it can go straight back into
        # `load_scenario` to carry on exploring interactively
        "final_state": sim.to_scenario(),
    }
