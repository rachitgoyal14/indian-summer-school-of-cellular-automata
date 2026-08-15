"""
test_ws_protocol.py — Stage 12 WebSocket API and state-schema extensions.

Everything built in Stages 9–11 reaching the wire: street groupings in the
`network` message, lane-change fields and `mode` in `state`, partial parameter
updates, batch runs with typed errors, and the guarantee that a client which
ignores every new field still works exactly as before.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.engine.simulation import Simulation
from src.server.state_serializer import serialize_network, serialize_state
# NOTE: reach the manager through the module. test_server.py rebinds
# `ws_server.manager`, so a by-value import goes stale mid-session.
from src.server import ws_server
from src.server.ws_server import app


MULTILANE = {"rows": 2, "cols": 2, "seg": 40, "lanes_per_direction": 2}


def multilane_sim(**kwargs) -> Simulation:
    return Simulation(config="grid", density=0.3, car_fraction=0.3, seed=4,
                      build_kwargs=MULTILANE, **kwargs)


def batch_spec(steps: int = 30, **batch) -> dict:
    return {
        "config": "grid", "seed": 7, "density": 0.3, "car_fraction": 0.3,
        "lane_change_prob": 0.3,
        "build_kwargs": {"rows": 2, "cols": 2, "seg": 30},
        "batch": {"steps": steps, **batch},
    }


def connect(sim: Simulation, paused: bool = True):
    """Install `sim` as the live simulation and hand back a client factory."""
    ws_server.manager.sim = sim
    if paused:
        ws_server.manager.sim.pause()
    return TestClient(app)


def drain_until(ws, predicate, limit: int = 40):
    """Read messages until one satisfies `predicate`. Returns it, or fails."""
    for _ in range(limit):
        msg = ws.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError(f"no matching message in {limit} reads")


# ------------------------------------------------------------ network message
def test_network_message_carries_streets():
    msg = serialize_network(multilane_sim())

    assert len(msg["streets"]) == 12
    street = msg["streets"][0]
    assert set(street) == {"id", "baseline", "centerline_path", "lane_width",
                           "n_forward", "n_backward", "lanes"}
    assert (street["n_forward"], street["n_backward"]) == (2, 0)
    assert street["lane_width"] > 0
    assert set(street["baseline"]) == {"x0", "y0", "x1", "y1"}
    # A grid street is straight, so it carries no centreline polyline and the
    # renderer falls back to `baseline`. Curved (imported) streets carry one —
    # see test_multilane_import.
    assert street["centerline_path"] == []

    lanes = street["lanes"]
    assert [l["lane_index"] for l in lanes] == [0, 1]
    assert all(l["direction"] == "forward" for l in lanes)
    # adjacency is stated outright, not left to be inferred from coordinates
    assert lanes[0]["left_road_id"] is None
    assert lanes[0]["right_road_id"] == lanes[1]["road_id"]
    assert lanes[1]["left_road_id"] == lanes[0]["road_id"]
    assert lanes[1]["right_road_id"] is None

    # every lane in the streets block is a real road in the same message
    road_ids = {r["id"] for r in msg["roads"]}
    for s in msg["streets"]:
        assert {l["road_id"] for l in s["lanes"]} <= road_ids


def test_network_roads_report_their_street():
    msg = serialize_network(multilane_sim())
    by_id = {r["id"]: r for r in msg["roads"]}
    for street in msg["streets"]:
        for lane in street["lanes"]:
            road = by_id[lane["road_id"]]
            assert road["street_id"] == street["id"]
            assert road["lane_index"] == lane["lane_index"]


def test_single_lane_network_has_an_empty_streets_block():
    msg = serialize_network(Simulation(config="one_way", seed=1))
    assert msg["streets"] == []
    assert all(r["street_id"] is None for r in msg["roads"])


def test_two_way_street_reports_both_directions():
    from src.mapdata.osm_to_network import osm_to_network

    nodes = {1: {"lat": 25.26, "lon": 82.990},
             2: {"lat": 25.26, "lon": 82.994},
             3: {"lat": 25.26, "lon": 82.998}}
    ways = [{"id": 1, "nodes": [1, 2], "tags": {"highway": "primary",
                                                "lanes": "4"}},
            {"id": 2, "nodes": [2, 3], "tags": {"highway": "primary",
                                                "lanes": "4"}}]
    sim = Simulation()
    sim.network = osm_to_network({"nodes": nodes, "ways": ways})

    streets = serialize_network(sim)["streets"]
    assert streets, "no streets serialized"
    wide = [s for s in streets if s["n_forward"] == 2 and s["n_backward"] == 2]
    assert wide, [(s["n_forward"], s["n_backward"]) for s in streets]
    assert len(wide[0]["lanes"]) == 4


# -------------------------------------------------------------- state message
def test_state_message_carries_lane_fields():
    sim = multilane_sim(lane_change_prob=0.4, rear_safety_gap=1)
    msg = serialize_state(sim)
    assert msg["mode"] == "live"
    assert msg["lane_change_prob"] == 0.4
    assert msg["rear_safety_gap"] == 1
    assert msg["lane_change_require_gain"] is True
    assert msg["lane_changes"] == 0
    sim.advance(30)
    assert serialize_state(sim)["lane_changes"] == sim.network.last_lane_changes


def test_state_message_shape_is_unchanged_for_old_clients():
    """Every pre-Stage-9 key a frontend already reads is still present."""
    msg = serialize_state(Simulation(config="one_way", seed=1))
    for key in ("type", "step", "running", "steps_per_second", "roads",
                "junctions", "disruptions", "analytics"):
        assert key in msg, key
    for key in ("id", "cells", "vehicles", "segments"):
        assert key in msg["roads"][0], key


# --------------------------------------------------- set_lane_change_params
@pytest.mark.parametrize("payload, expected", [
    ({"probability": 0.35}, (0.35, 0, True)),
    ({"prob": 0.35}, (0.35, 0, True)),                    # short alias
    ({"rear_safety_gap": 2}, (0.0, 2, True)),
    ({"rear_gap": 2}, (0.0, 2, True)),                    # short alias
    ({"require_gain": False}, (0.0, 0, False)),
    ({"probability": 0.5, "rear_safety_gap": 1, "require_gain": False},
     (0.5, 1, False)),
])
def test_set_lane_change_params_over_the_socket(payload, expected):
    with connect(multilane_sim()) as client, \
            client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "set_lane_change_params", **payload})
        state = drain_until(ws, lambda m: m.get("type") == "state"
                            and m.get("lane_change_prob") == expected[0]
                            and m.get("rear_safety_gap") == expected[1]
                            and m.get("lane_change_require_gain") == expected[2])
        assert state["mode"] == "live"

    net = ws_server.manager.sim.network
    assert (net.lane_change_prob, net.rear_safety_gap,
            net.lane_change_require_gain) == expected


def test_partial_update_leaves_the_other_params_alone():
    sim = multilane_sim(lane_change_prob=0.6, rear_safety_gap=3,
                        lane_change_require_gain=False)
    with connect(sim) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "set_lane_change_params", "probability": 0.1})
        drain_until(ws, lambda m: m.get("lane_change_prob") == 0.1)

    assert ws_server.manager.sim.rear_safety_gap == 3
    assert ws_server.manager.sim.lane_change_require_gain is False


def test_params_take_effect_on_the_next_tick():
    sim = multilane_sim(lane_change_prob=0.0)
    sim.set_speed(60.0)
    with connect(sim, paused=False) as client, \
            client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "set_lane_change_params", "probability": 1.0})
        state = drain_until(ws, lambda m: m.get("lane_change_prob") == 1.0)
        before = state["step"]
        # a later tick reports lateral activity the old value could not produce
        later = drain_until(ws, lambda m: m.get("type") == "state"
                            and m["step"] > before
                            and m["lane_changes"] > 0, limit=120)
        assert later["lane_change_prob"] == 1.0


# ------------------------------------------------------------- run_scenario
def test_run_scenario_returns_a_result():
    with connect(Simulation(config="one_way", seed=1)) as client, \
            client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "run_scenario", "scenario": batch_spec(steps=30)})
        reply = drain_until(ws, lambda m: m.get("type") == "scenario_result")

    assert reply["mode"] == "batch"
    assert len(reply["trajectory"]) == 31
    assert reply["summary"]["steps"] == 30
    for key in ("peak_flow", "mean_flow", "steady_state_flow", "min_entropy",
                "final_landscape", "total_lane_changes", "total_spawned",
                "total_exited", "events_fired", "elapsed_seconds"):
        assert key in reply["summary"], key

    # the result carries the world in the live `network` shape as well
    assert reply["network"]["type"] == "network"
    assert reply["network"]["roads"]
    assert "streets" in reply["network"]
    assert reply["final_state"]["roads"], "final_state must stay loadable"


def test_scenario_result_final_state_resumes_live():
    """Loading the result must land exactly where the batch stopped."""
    spec = batch_spec(steps=40)
    with connect(Simulation(config="one_way", seed=1)) as client, \
            client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "run_scenario", "scenario": spec})
        reply = drain_until(ws, lambda m: m.get("type") == "scenario_result")

        ws.send_json({"type": "load_scenario", "data": reply["final_state"]})
        drain_until(ws, lambda m: m.get("type") == "state" and m["step"] == 40)

    resumed = ws_server.manager.sim
    assert resumed.step_count == 40

    # continuing live must match continuing the batch by another 30 steps
    longer = dict(spec, batch={"steps": 70})
    from src.engine.scenario_runner import run_scenario

    expected = run_scenario(longer)["final_state"]
    resumed.advance(30)
    assert resumed.to_scenario() == expected


def test_run_scenario_with_multilane_streets_round_trips():
    spec = batch_spec(steps=25)
    spec["build_kwargs"] = MULTILANE
    with connect(Simulation(config="one_way", seed=1)) as client, \
            client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "run_scenario", "scenario": spec})
        reply = drain_until(ws, lambda m: m.get("type") == "scenario_result")

        assert len(reply["network"]["streets"]) == 12
        ws.send_json({"type": "load_scenario", "data": reply["final_state"]})
        network = drain_until(ws, lambda m: m.get("type") == "network")

    assert len(network["streets"]) == 12
    assert len(ws_server.manager.sim.network.streets) == 12
    ws_server.manager.sim.advance(5)          # the reconstructed world still simulates


# ------------------------------------------------------------ scenario_error
@pytest.mark.parametrize("scenario, code, fragment", [
    ({"config": "grid", "batch": {"steps": 10}}, "INVALID_CONFIG", "seed"),
    ({"config": "nope", "seed": 1, "batch": {"steps": 5}},
     "INVALID_CONFIG", "unknown config"),
    ({"config": "grid", "seed": 1, "batch": {"steps": 100000}},
     "OVERSIZED_REQUEST", "more than"),
    ({}, "INVALID_CONFIG", "steps"),
])
def test_scenario_error_codes(scenario, code, fragment):
    live = Simulation(config="one_way", density=0.2, seed=1)
    with connect(live) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        before = ws_server.manager.sim.to_scenario()

        ws.send_json({"type": "run_scenario", "scenario": scenario})
        reply = drain_until(ws, lambda m: m.get("type") == "scenario_error")
        assert reply["code"] == code
        assert fragment in reply["message"]
        assert reply["error"] == reply["message"]   # legacy alias

        # socket and live simulation both survive
        ws.send_json({"type": "ping", "t": 9.0})
        assert drain_until(ws, lambda m: m.get("type") == "pong")["t"] == 9.0
        assert ws_server.manager.sim.to_scenario() == before


def test_concurrent_batch_is_rejected_with_already_running():
    heavy = {
        "config": "grid", "seed": 7, "density": 0.3,
        "build_kwargs": {"rows": 8, "cols": 8, "seg": 20},
        "batch": {"steps": 600},
    }
    live = Simulation(config="one_way", density=0.2, seed=1)
    with connect(live) as client, \
            client.websocket_connect("/ws") as a, \
            client.websocket_connect("/ws") as b:
        for ws in (a, b):
            ws.receive_json()
            ws.receive_json()
        before = ws_server.manager.sim.to_scenario()

        a.send_json({"type": "run_scenario", "scenario": heavy})
        b.send_json({"type": "run_scenario", "scenario": batch_spec(steps=5)})

        replies = {}
        for ws in (a, b):
            msg = drain_until(ws, lambda m: m.get("type", "").startswith("scenario_"))
            replies[msg["type"]] = msg

        assert set(replies) == {"scenario_result", "scenario_error"}
        assert replies["scenario_error"]["code"] == "ALREADY_RUNNING"
        assert "already running" in replies["scenario_error"]["message"]
        assert ws_server.manager.sim.to_scenario() == before


# ------------------------------------------------------------- import_result
def test_import_result_reports_lane_counts(monkeypatch):
    """`import_region` must report street-level lane detail, not just roads."""
    nodes = {1: {"lat": 25.26, "lon": 82.990},
             2: {"lat": 25.26, "lon": 82.994},
             3: {"lat": 25.26, "lon": 82.998},
             4: {"lat": 25.264, "lon": 82.994}}
    ways = [
        {"id": 1, "nodes": [1, 2], "tags": {"highway": "primary", "lanes": "4"}},
        {"id": 2, "nodes": [2, 3], "tags": {"highway": "primary", "lanes": "2"}},
        {"id": 3, "nodes": [2, 4], "tags": {"highway": "residential"}},
    ]
    monkeypatch.setattr("src.mapdata.geocode.geocode",
                        lambda place: (25.25, 82.98, 25.27, 83.00))
    monkeypatch.setattr("src.mapdata.overpass_client.fetch_roads",
                        lambda *a, **k: {"nodes": nodes, "ways": ways})

    sim = Simulation()
    result = sim.import_region("Somewhere")

    assert result["ok"] is True
    assert result["streets"] >= 3
    assert result["multi_lane_streets"] >= 1       # the lanes=4 avenue
    assert result["max_lanes_per_direction"] == 2
    assert result["two_way_streets"] >= 3
    # the pre-Stage-12 keys are still there for an old client
    for key in ("roads", "junctions", "total_cells", "error"):
        assert key in result, key


def test_import_result_is_broadcast_over_the_socket(monkeypatch):
    monkeypatch.setattr("src.mapdata.geocode.geocode", lambda place: None)
    with connect(Simulation(config="one_way", seed=1)) as client, \
            client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "import_region", "place_name": "Nowhere At All"})
        reply = drain_until(ws, lambda m: m.get("type") == "import_result")
    assert reply["ok"] is False
    assert "geocode" in reply["error"].lower()


# --------------------------------------------------------- backward compat
def test_old_client_flow_still_works():
    """
    A frontend that knows nothing about streets, lane changes or batch mode
    must still connect, drive the sim, and read every field it used to.
    """
    sim = multilane_sim(lane_change_prob=0.4)
    sim.set_speed(60.0)
    with connect(sim, paused=False) as client, \
            client.websocket_connect("/ws") as ws:
        network = ws.receive_json()
        state = ws.receive_json()
        assert network["type"] == "network" and state["type"] == "state"

        # the old renderer reads roads + junctions only, and both still work
        assert all({"id", "length", "geometry", "periodic"} <= set(r)
                   for r in network["roads"])
        assert all({"id", "x", "y"} <= set(j) for j in network["junctions"])

        for message in ({"type": "pause"}, {"type": "step"},
                        {"type": "set_speed", "steps_per_second": 20},
                        {"type": "resume"}):
            ws.send_json(message)
        state = drain_until(ws, lambda m: m.get("type") == "state")
        assert state["analytics"]["density"] >= 0.0
        assert json.dumps(state)          # still plain JSON


def test_serialized_messages_are_json_safe():
    sim = multilane_sim(lane_change_prob=0.3)
    sim.advance(5)
    for payload in (serialize_network(sim), serialize_state(sim)):
        assert json.loads(json.dumps(payload)) == payload
