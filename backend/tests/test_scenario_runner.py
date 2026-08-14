"""
test_scenario_runner.py — Stage 10 batch ("what-if") scenario engine.

The guarantees under test:
  - a batch run is bit-for-bit identical to stepping the same config live,
  - the same seed always gives the same trajectory,
  - a batch run leaves the live simulation completely untouched,
  - scheduled events fire deterministically at the step they name,
  - bad specs come back as clear errors instead of taking the server down,
  - 50 consecutive runs do not accumulate memory.
"""

from __future__ import annotations

import gc
import hashlib
import json
import time
import tracemalloc

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.engine.scenario_runner import (
    MAX_STEPS,
    ScenarioError,
    build_simulation,
    run_scenario,
    validate,
)
from src.engine.simulation import Simulation
from src.network.street import FORWARD, Street
# NOTE: reach the manager through the module. test_server.py rebinds
# `ws_server.manager`, so a by-value import goes stale mid-session.
from src.server import ws_server
from src.server.ws_server import app


# --------------------------------------------------------------------- helpers
def grid_spec(steps: int = 50, **batch) -> dict:
    return {
        "config": "grid",
        "seed": 7,
        "density": 0.3,
        "car_fraction": 0.3,
        "lane_change_prob": 0.3,
        "build_kwargs": {"rows": 3, "cols": 3, "seg": 30},
        "batch": {"steps": steps, **batch},
    }


def ring_spec(steps: int = 50, **batch) -> dict:
    return {
        "config": "one_way",
        "seed": 3,
        "length": 120,
        "density": 0.35,
        "car_fraction": 0.3,
        "batch": {"steps": steps, **batch},
    }


def fingerprint(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def positions(sim: Simulation) -> list[tuple]:
    return [
        (r.id, v.front, v.length, v.vtype)
        for r in sim.network.roads_ordered()
        for v in sorted(r.vehicles, key=lambda v: v.front)
    ]


# ------------------------------------------------------------------ structure
def test_result_shape():
    result = run_scenario(grid_spec(steps=40))
    assert set(result) == {"trajectory", "snapshots", "summary", "final_state"}

    # a record per step, plus the initial state at step 0
    assert len(result["trajectory"]) == 41
    assert [r["step"] for r in result["trajectory"]] == list(range(41))
    for key in ("density", "flow", "entropy", "entropy_bits", "blocked_fraction",
                "avg_queue", "landscape", "lane_changes", "spawned", "exited",
                "vehicles"):
        assert key in result["trajectory"][0], key

    # heavy data defaults to first / middle / final only
    assert [s["step"] for s in result["snapshots"]] == [0, 20, 40]
    assert "segments" in result["snapshots"][0]["roads"][0]

    for key in ("steps", "records", "peak_flow", "mean_flow", "steady_state_flow",
                "min_entropy", "max_entropy", "final_density", "final_landscape",
                "peak_avg_queue", "total_lane_changes", "total_spawned",
                "total_exited", "events_fired", "elapsed_seconds"):
        assert key in result["summary"], key

    # the whole result must be JSON-serialisable for the WebSocket
    json.dumps(result)


def test_sampling_controls():
    result = run_scenario(grid_spec(steps=100, record_every=10))
    assert [r["step"] for r in result["trajectory"]] == list(range(0, 101, 10))

    result = run_scenario(grid_spec(steps=100, record_every=30))
    # the final step is always recorded, even off-stride
    assert [r["step"] for r in result["trajectory"]] == [0, 30, 60, 90, 100]

    result = run_scenario(grid_spec(steps=100, snapshot_every=25))
    assert [s["step"] for s in result["snapshots"]] == [0, 25, 50, 75, 100]

    result = run_scenario(grid_spec(steps=20, include_segments=False))
    assert "segments" not in result["snapshots"][0]["roads"][0]
    assert "vehicles" in result["snapshots"][0]["roads"][0]


# ----------------------------------------------------------------- determinism
def test_ten_runs_identical():
    specs = [grid_spec(steps=60) for _ in range(10)]
    results = [run_scenario(s) for s in specs]

    traj = {fingerprint(r["trajectory"]) for r in results}
    final = {fingerprint(r["final_state"]) for r in results}
    assert len(traj) == 1, "trajectories diverged across identical runs"
    assert len(final) == 1, "final states diverged across identical runs"


def test_different_seed_diverges():
    a = run_scenario(grid_spec(steps=60))
    b = grid_spec(steps=60)
    b["seed"] = 8
    assert fingerprint(a["trajectory"]) != fingerprint(run_scenario(b)["trajectory"])


# ------------------------------------------------------------ live equivalence
@pytest.mark.parametrize("spec_fn", [ring_spec, grid_spec])
def test_batch_matches_live_stepping(spec_fn):
    """100 batch steps == 100 live steps, positions, occupancy and analytics."""
    spec = spec_fn(steps=100)
    result = run_scenario(spec)

    live = build_simulation(spec)
    trajectory = []
    from src.engine.scenario_runner import _record
    trajectory.append(_record(live, 0))
    for i in range(1, 101):
        live.advance(1)
        trajectory.append(_record(live, i))

    assert result["trajectory"] == trajectory
    assert result["final_state"] == live.to_scenario()

    batch_sim = Simulation()
    batch_sim.apply_scenario(result["final_state"])
    assert positions(batch_sim) == positions(live)
    for a, b in zip(batch_sim.network.roads_ordered(), live.network.roads_ordered()):
        assert np.array_equal(a.occupancy(), b.occupancy())


def test_lane_changes_are_recorded():
    spec = grid_spec(steps=80)
    spec["lane_change_prob"] = 0.0
    assert run_scenario(spec)["summary"]["total_lane_changes"] == 0


# --------------------------------------------------------------------- events
def test_scheduled_block_and_clear():
    """The hand-editable case: flood at step 20, cleared at step 40."""
    spec = ring_spec(steps=60, schedule=[
        {"step": 20, "action": "block_cells", "road_id": 0,
         "cells": [50, 51, 52], "permanent": True, "kind": "flood"},
        {"step": 40, "action": "clear_disruptions", "kind": "flood"},
    ])
    result = run_scenario(spec)
    blocked = {r["step"]: r["blocked_fraction"] for r in result["trajectory"]}

    assert blocked[19] == 0.0                  # before the flood
    assert blocked[20] > 0.0                   # fires *before* step 20 runs
    assert blocked[39] > 0.0                   # still there
    assert blocked[40] == 0.0                  # cleared
    assert [e["step"] for e in result["summary"]["events_fired"]] == [20, 40]
    assert result["summary"]["events_fired"][0]["cells"] == [50, 51, 52]


def test_scheduled_source_rate_change():
    spec = grid_spec(steps=60, schedule=[
        {"step": 30, "action": "set_source_rate", "road_id": 0, "value": 0.0},
    ])
    result = run_scenario(spec)
    fired = result["summary"]["events_fired"]
    assert fired[0]["road_id"] == 0 and fired[0]["value"] == 0.0


def test_scheduled_lane_change_params():
    spec = grid_spec(steps=40, schedule=[
        {"step": 10, "action": "set_lane_change_params", "prob": 0.9,
         "rear_gap": 2},
    ])
    result = run_scenario(spec)
    assert result["final_state"]["lane_change_prob"] == 0.9
    assert result["final_state"]["rear_safety_gap"] == 2


def test_events_are_deterministic():
    spec = grid_spec(steps=60, schedule=[
        {"step": 10, "action": "trigger_disruption", "kind": "accident"},
        {"step": 30, "action": "set_disruption_params",
         "probs": {"breakdown": 0.05}, "repair_scale": 0.5},
        {"step": 45, "action": "clear_disruptions"},
    ])
    runs = [fingerprint(run_scenario(spec)["trajectory"]) for _ in range(5)]
    assert len(set(runs)) == 1


# ------------------------------------------------------------------- isolation
def test_batch_does_not_touch_the_live_simulation():
    live = Simulation(config="grid", density=0.3, seed=42)
    for _ in range(10):
        live.advance()

    before = {
        "scenario": live.to_scenario(),
        "rng": live._rng.bit_generator.state,
        "positions": positions(live),
        "step": live.step_count,
    }

    run_scenario(grid_spec(steps=200))

    assert live.to_scenario() == before["scenario"]
    assert live._rng.bit_generator.state == before["rng"]
    assert positions(live) == before["positions"]
    assert live.step_count == before["step"]


def test_branching_from_a_live_state_leaves_it_alone():
    """`sim.to_scenario()` is a pure-data deep copy: batch it, live is safe."""
    live = Simulation(config="one_way", length=120, density=0.35, seed=4)
    for _ in range(15):
        live.advance()

    spec = live.to_scenario()
    spec["batch"] = {"steps": 100}
    before = positions(live)

    result = run_scenario(spec)

    assert positions(live) == before, "the live world moved"
    assert live.step_count == 15
    # the batch really did continue from where live was
    assert result["final_state"]["step"] == 115


# --------------------------------------------------------------- error handling
@pytest.mark.parametrize("spec, message", [
    ({"config": "grid", "batch": {"steps": 10}}, "seed"),
    ({"config": "grid", "seed": 1}, "steps"),
    ({"config": "grid", "seed": 1, "batch": {"steps": 0}}, "between"),
    ({"config": "grid", "seed": 1, "batch": {"steps": MAX_STEPS + 1}}, "between"),
    ({"config": "nope", "seed": 1, "batch": {"steps": 5}}, "unknown config"),
    ({"config": "grid", "seed": 1, "density": -0.5, "batch": {"steps": 5}},
     "between"),
    ({"config": "grid", "seed": 1, "density": 1.5, "batch": {"steps": 5}},
     "between"),
    ({"config": "grid", "seed": 1, "lane_change_prob": 2.0, "batch": {"steps": 5}},
     "between"),
    ({"config": "grid", "seed": 1,
      "batch": {"steps": 5, "schedule": [{"step": 1, "action": "explode"}]}},
     "unknown action"),
    ({"config": "grid", "seed": 1,
      "batch": {"steps": 5, "schedule": [{"step": 99, "action": "clear_disruptions"}]}},
     "'step' must be"),
    ({"config": "grid", "seed": 1,
      "batch": {"steps": 5, "schedule": [{"step": 1, "action": "set_source_rate",
                                          "value": 0.5}]}},
     "requires 'road_id'"),
    ({"config": "grid", "seed": 1,
      "batch": {"steps": 5, "schedule": [{"step": 1, "action": "trigger_disruption",
                                          "kind": "earthquake"}]}},
     "unknown disruption kind"),
    ({"config": "grid", "seed": 1, "batch": {"steps": 5, "schedule": "nope"}},
     "must be a list"),
    ({"config": "grid", "seed": 1,
      "batch": {"steps": 100000, "record_every": 1}}, "more than"),
    ("not a dict", "must be a JSON object"),
])
def test_invalid_specs_are_rejected_before_anything_runs(spec, message):
    with pytest.raises(ScenarioError) as exc:
        run_scenario(spec)
    assert message in str(exc.value)


def test_unknown_road_id_in_event_is_reported_clearly():
    spec = grid_spec(steps=10, schedule=[
        {"step": 2, "action": "set_source_rate", "road_id": 9999, "value": 0.5},
    ])
    with pytest.raises(ScenarioError, match="unknown road id"):
        run_scenario(spec)


def test_out_of_range_cells_in_event_are_reported_clearly():
    spec = ring_spec(steps=10, schedule=[
        {"step": 2, "action": "block_cells", "road_id": 0, "cells": [5, 9999]},
    ])
    with pytest.raises(ScenarioError, match="outside road 0"):
        run_scenario(spec)


def test_validate_returns_normalised_batch_settings():
    settings = validate(grid_spec(steps=10))
    assert settings == {"steps": 10, "record_every": 1, "snapshot_every": 0,
                        "include_segments": True, "schedule": []}


# ---------------------------------------------------------------- round-tripping
def test_full_scenario_with_lane_groups_round_trips():
    sim = Simulation(config="two_way_no_interaction", density=0.3,
                     car_fraction=0.3, seed=11, lane_change_prob=0.5,
                     rear_safety_gap=1)
    street = Street("S")
    for rid in sorted(sim.network.roads):
        street.add_road(sim.network.roads[rid], direction=FORWARD)
    sim.network.add_street(street)

    spec = sim.to_scenario()
    spec["batch"] = {"steps": 80, "schedule": [
        {"step": 20, "action": "trigger_disruption", "kind": "flood"},
        {"step": 60, "action": "clear_disruptions", "kind": "flood"},
    ]}

    reloaded = json.loads(json.dumps(spec))
    assert reloaded == spec, "spec is not JSON-stable"

    first = run_scenario(spec)
    second = run_scenario(reloaded)
    assert fingerprint(first["trajectory"]) == fingerprint(second["trajectory"])
    assert first["final_state"] == second["final_state"]

    # the lane grouping survived into the result
    assert first["final_state"]["streets"][0]["id"] == "S"
    assert len(first["final_state"]["streets"][0]["lanes"]) == 2


def test_final_state_can_resume_live_exploration():
    result = run_scenario(grid_spec(steps=50))
    sim = Simulation()
    sim.apply_scenario(result["final_state"])
    assert sim.step_count == 50
    sim.advance(5)
    assert sim.step_count == 55


# ------------------------------------------------------------------ resources
@pytest.mark.parametrize("_", range(1))
def test_fifty_consecutive_runs_do_not_leak(_):
    spec = ring_spec(steps=40)
    run_scenario(spec)  # warm up caches/imports before measuring
    gc.collect()
    tracemalloc.start()
    try:
        baseline = tracemalloc.take_snapshot()
        for _ in range(10):
            run_scenario(spec)
        gc.collect()
        after_ten = sum(s.size for s in
                        tracemalloc.take_snapshot().compare_to(baseline, "filename"))
        for _ in range(40):
            run_scenario(spec)
        gc.collect()
        after_fifty = sum(s.size for s in
                          tracemalloc.take_snapshot().compare_to(baseline, "filename"))
    finally:
        tracemalloc.stop()

    # 40 more runs must not cost meaningfully more than the first 10 did:
    # memory plateaus instead of growing with the number of runs.
    assert after_fifty < after_ten + 4_000_000, (
        f"memory grew with run count: {after_ten} -> {after_fifty} bytes"
    )


@pytest.mark.slow
def test_large_network_runs_in_time():
    """500 steps on an IIT (BHU)-scale network (264 roads, 3696 cells) < 2s."""
    spec = {
        "config": "grid", "seed": 7, "density": 0.3, "car_fraction": 0.3,
        "lane_change_prob": 0.3,
        "build_kwargs": {"rows": 11, "cols": 11, "seg": 14},
        "batch": {"steps": 500},
    }
    sim = build_simulation(spec)
    assert len(sim.network.roads) == 264
    assert sum(r.length for r in sim.network.roads.values()) == 3696

    started = time.perf_counter()
    result = run_scenario(spec)
    elapsed = time.perf_counter() - started

    assert len(result["trajectory"]) == 501
    assert elapsed < 2.0, f"took {elapsed:.2f}s, budget is 2.0s"


# ------------------------------------------------------------------- websocket
def test_websocket_run_scenario():
    ws_server.manager.sim = Simulation(config="one_way", density=0.2, seed=1)
    ws_server.manager.sim.pause()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()  # network
        ws.receive_json()  # state
        ws.send_json({"type": "run_scenario", "scenario": grid_spec(steps=40)})

        reply = ws.receive_json()
        assert reply["type"] == "scenario_result"
        assert len(reply["trajectory"]) == 41
        assert reply["summary"]["steps"] == 40
        assert reply["final_state"]["roads"]

        # the result is a valid live scenario: promote it and keep exploring
        ws.send_json({"type": "load_scenario", "data": reply["final_state"]})
        ws.receive_json()  # network (structural rebroadcast)
        state = ws.receive_json()
        assert state["type"] == "state" and state["step"] == 40

    assert ws_server.manager.sim.step_count == 40


def test_websocket_scenario_error_does_not_kill_the_server():
    ws_server.manager.sim = Simulation(config="one_way", density=0.2, seed=1)
    ws_server.manager.sim.pause()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        before = ws_server.manager.sim.to_scenario()

        ws.send_json({"type": "run_scenario",
                      "scenario": {"config": "grid", "batch": {"steps": 10}}})
        reply = ws.receive_json()
        assert reply["type"] == "scenario_error"
        assert "seed" in reply["error"]

        # the socket and the live simulation are both still healthy
        ws.send_json({"type": "ping", "t": 1.5})
        assert ws.receive_json() == {"type": "pong", "t": 1.5}
        assert ws_server.manager.sim.to_scenario() == before


def test_live_stream_continues_during_a_batch_run():
    """
    Client A watches the live stream; client B fires a long batch. A's stream
    must keep advancing throughout, and B must get exactly one scenario_result
    — every other message it sees is an ordinary *live* state, never one of
    the batch's 400 internal steps.
    """
    ws_server.manager.sim = Simulation(config="grid", density=0.3, seed=2)
    ws_server.manager.sim.set_speed(60.0)
    with TestClient(app) as client, \
            client.websocket_connect("/ws") as a, \
            client.websocket_connect("/ws") as b:
        for ws in (a, b):
            ws.receive_json()
            ws.receive_json()

        heavy = {
            "config": "grid", "seed": 7, "density": 0.3, "car_fraction": 0.3,
            "build_kwargs": {"rows": 8, "cols": 8, "seg": 20},
            "batch": {"steps": 400},
        }
        b.send_json({"type": "run_scenario", "scenario": heavy})

        # A keeps receiving live states with a strictly advancing step counter
        steps = []
        while len(steps) < 8:
            msg = a.receive_json()
            if msg.get("type") == "state":
                steps.append(msg["step"])
        assert steps == sorted(steps) and steps[-1] > steps[0], steps

        # B is a live subscriber too, so it keeps seeing live states — but the
        # batch itself streams nothing: one result, no batch intermediates.
        seen = []
        while True:
            msg = b.receive_json()
            if msg.get("type") == "scenario_result":
                break
            seen.append(msg)
        assert msg["summary"]["steps"] == 400
        assert all(m.get("type") == "state" for m in seen), \
            {m.get("type") for m in seen}
        # live ticks during the run, not 400 batch broadcasts
        assert len(seen) < 100, f"{len(seen)} messages arrived during the batch"
        assert all(m["step"] <= ws_server.manager.sim.step_count for m in seen)


def test_websocket_rejects_a_concurrent_batch():
    ws_server.manager.sim = Simulation(config="one_way", density=0.2, seed=1)
    ws_server.manager.sim.pause()
    with TestClient(app) as client, \
            client.websocket_connect("/ws") as a, \
            client.websocket_connect("/ws") as b:
        for ws in (a, b):
            ws.receive_json()
            ws.receive_json()

        heavy = {
            "config": "grid", "seed": 7, "density": 0.3,
            "build_kwargs": {"rows": 8, "cols": 8, "seg": 20},
            "batch": {"steps": 600},
        }
        a.send_json({"type": "run_scenario", "scenario": heavy})
        b.send_json({"type": "run_scenario", "scenario": grid_spec(steps=5)})

        replies = {a.receive_json()["type"], b.receive_json()["type"]}
        assert replies == {"scenario_result", "scenario_error"}
