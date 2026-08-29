"""
test_server.py — Stage 2 WebSocket server tests.

Uses FastAPI's TestClient, which drives the real ASGI app (including the
background tick loop) over an in-process WebSocket. This automates the
server side of Stage 2's acceptance: state streaming, control messages,
message schema, and monotonic step ordering. The *browser* rendering /
zoom-pan / video parts remain manual (documented in PHASE_REPORT).
"""

from __future__ import annotations

import os
import threading
import time
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient

from src.engine.simulation import Simulation
from src.server import ws_server
from src.server.state_serializer import serialize_network, serialize_state


# ===========================================================================
# Serializer schema (no server needed)
# ===========================================================================

def test_network_message_schema():
    sim = Simulation(length=50, density=0.2, seed=1)
    msg = serialize_network(sim)
    assert msg["type"] == "network"
    assert isinstance(msg["roads"], list) and len(msg["roads"]) == 1
    r = msg["roads"][0]
    assert r["id"] == 0
    assert r["length"] == 50
    assert set(r["geometry"]) == {"x0", "y0", "dx", "dy"}
    assert r["periodic"] is True
    assert msg["junctions"] == []  # Stage 3 placeholder present


def test_state_message_schema_and_types():
    sim = Simulation(length=40, density=0.25, seed=2)
    msg = serialize_state(sim)
    assert msg["type"] == "state"
    assert msg["step"] == 0
    assert msg["running"] is True
    assert isinstance(msg["steps_per_second"], float)
    cells = msg["roads"][0]["cells"]
    assert len(cells) == 40
    # cells must be plain python ints (JSON-safe), only 0/1 in Stage 2
    assert all(isinstance(c, int) for c in cells)
    assert set(cells) <= {0, 1}
    assert "density" in msg["analytics"] and "flow" in msg["analytics"]
    # exactly round(0.25*40)=10 vehicles
    assert sum(cells) == 10


# ===========================================================================
# Simulation engine control semantics (no server needed)
# ===========================================================================

def test_advance_increments_step_and_conserves_vehicles():
    sim = Simulation(length=200, density=0.3, seed=5)
    n0 = int(sim.roads[0].cells.sum())
    sim.advance(10)
    assert sim.step_count == 10
    # Rule 184 on a periodic road conserves the number of vehicles exactly.
    assert int(sim.roads[0].cells.sum()) == n0


def test_pause_resume_single_step():
    sim = Simulation(length=100, density=0.3, seed=5)
    sim.pause()
    assert sim.running is False
    sim.single_step()
    assert sim.step_count == 1  # single_step works even while paused
    sim.resume()
    assert sim.running is True


def test_reset_is_reproducible_and_sets_density():
    sim = Simulation(length=100, density=0.3, seed=9)
    sim.advance(20)
    sim.reset(density=0.5, seed=123)
    assert sim.step_count == 0
    a = sim.roads[0].cells.copy()
    assert a.sum() == 50
    sim.reset(density=0.5, seed=123)
    b = sim.roads[0].cells
    assert np.array_equal(a, b)  # same seed → identical initial state


def test_set_speed_clamped():
    sim = Simulation()
    sim.set_speed(1000)
    assert sim.steps_per_second == 120.0
    sim.set_speed(0.0)
    assert sim.steps_per_second == 0.5


# ===========================================================================
# End-to-end over a real (in-process) WebSocket
# ===========================================================================

@pytest.fixture()
def client():
    # Fresh manager/sim per test so tests don't share tick state.
    ws_server.manager = ws_server.SimulationManager(
        Simulation(length=120, density=0.3, seed=7)
    )
    with TestClient(ws_server.app) as c:
        yield c


def _recv_state(ws):
    """Receive messages until a 'state' arrives; return it."""
    for _ in range(50):
        msg = ws.receive_json()
        if msg["type"] == "state":
            return msg
    raise AssertionError("no state message received")


def test_ws_sends_network_then_state_on_connect(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "network"
        second = ws.receive_json()
        assert second["type"] == "state"
        assert second["step"] >= 0


def test_ws_steps_advance_monotonically(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # network
        steps = []
        for _ in range(6):
            steps.append(_recv_state(ws)["step"])
        # Monotonic non-decreasing, and it actually progressed.
        assert steps == sorted(steps)
        assert steps[-1] > steps[0]


def test_ws_pause_stops_progress_and_step_advances_once(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # network
        _recv_state(ws)
        ws.send_json({"type": "pause"})
        paused = _recv_state(ws)  # broadcast reflecting the pause
        assert paused["running"] is False
        # After pause, single explicit step advances by exactly one.
        ws.send_json({"type": "step"})
        after = _recv_state(ws)
        assert after["step"] == paused["step"] + 1


def test_ws_reset_density_takes_effect(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # network
        _recv_state(ws)
        ws.send_json({"type": "pause"})
        _recv_state(ws)
        ws.send_json({"type": "reset", "density": 0.5, "seed": 1})
        # reset broadcasts a network then a state; find the state
        st = _recv_state(ws)
        assert st["step"] == 0
        cells = st["roads"][0]["cells"]
        assert sum(cells) == round(0.5 * len(cells))


def test_ws_ping_pong_roundtrip(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # network
        ws.send_json({"type": "ping", "t": 987.5})
        # pong may arrive interleaved with state broadcasts; scan for it.
        for _ in range(50):
            msg = ws.receive_json()
            if msg["type"] == "pong":
                assert msg["t"] == 987.5
                break
        else:
            raise AssertionError("no pong received")


def test_import_region_does_not_block_the_event_loop(client, monkeypatch):
    """
    A slow import must not freeze the whole server.

    `Simulation.import_region` geocodes and queries Overpass with blocking
    urllib — up to ~85 s of timeouts in the worst case. It used to be called
    straight from the async handler, which stalled the event loop for that
    long: nothing else on any connection was served until the HTTP calls
    returned, so from a browser the import looked like it had never reached
    the handler at all.

    Note what is and is not promised. A connection reads its own messages in
    order, so the importing connection is legitimately busy until its import
    finishes, and the tick loop waits too — the import holds the simulation
    lock so the network swap is atomic. What must keep working is everything
    else, which is what a second connection here checks.
    """
    started = threading.Event()
    release = threading.Event()

    def slow_import(place_name):
        started.set()
        # Held open until the other connection has proved the loop is alive.
        release.wait(timeout=10)
        return {"ok": True, "error": None, "roads": 0,
                "junctions": 0, "total_cells": 0}

    monkeypatch.setattr(ws_server.manager.sim, "import_region", slow_import)

    with client.websocket_connect("/ws") as importer:
        importer.receive_json()  # network
        importer.send_json({"type": "import_region", "place_name": "Nowhere"})
        assert started.wait(timeout=5), "import never started"

        # A blocking import would take the event loop with it, and this second
        # connection would not be served until the import finished. The clock
        # is what makes that visible: without the fix the pong still arrives,
        # but only once `release.wait` times out ten seconds later.
        t0 = time.monotonic()
        with client.websocket_connect("/ws") as bystander:
            assert bystander.receive_json()["type"] == "network"
            bystander.send_json({"type": "ping", "t": 42.0})
            for _ in range(50):
                msg = bystander.receive_json()
                if msg["type"] == "pong":
                    assert msg["t"] == 42.0
                    break
            else:
                raise AssertionError("no pong while an import was in flight")
        waited = time.monotonic() - t0
        assert waited < 3.0, (
            f"a second connection waited {waited:.1f}s to be served while an "
            "import was in flight; the import is blocking the event loop"
        )

        release.set()

        for _ in range(200):
            msg = importer.receive_json()
            if msg["type"] == "import_result":
                assert msg["ok"] is True
                break
        else:
            raise AssertionError("no import_result after the import finished")


# ===========================================================================
# REST API endpoint tests
# ===========================================================================

def test_rest_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"


def test_rest_get_state_and_network(client):
    res_state = client.get("/api/state")
    assert res_state.status_code == 200
    state_data = res_state.json()
    assert state_data["type"] == "state"
    assert "roads" in state_data
    assert "analytics" in state_data

    res_net = client.get("/api/network")
    assert res_net.status_code == 200
    net_data = res_net.json()
    assert net_data["type"] == "network"
    assert "roads" in net_data


def test_rest_controls_lifecycle(client):
    # Pause
    res = client.post("/api/control/pause")
    assert res.status_code == 200
    assert res.json()["running"] is False

    # Step
    res = client.post("/api/control/step")
    assert res.status_code == 200
    assert "step" in res.json()

    # Resume
    res = client.post("/api/control/resume")
    assert res.status_code == 200
    assert res.json()["running"] is True

    # Speed
    res = client.post("/api/control/speed", json={"steps_per_second": 30.0})
    assert res.status_code == 200
    assert res.json()["steps_per_second"] == 30.0

    # Reset
    res = client.post("/api/control/reset", json={"density": 0.4, "seed": 42})
    assert res.status_code == 200
    assert res.json()["status"] == "reset"

    # Disruption
    res = client.post("/api/control/disruptions", json={"kind": "tree"})
    assert res.status_code == 200
    assert res.json()["kind"] == "tree"

    # Clear Disruptions
    res = client.post("/api/control/disruptions/clear")
    assert res.status_code == 200
    assert res.json()["status"] == "disruptions_cleared"

