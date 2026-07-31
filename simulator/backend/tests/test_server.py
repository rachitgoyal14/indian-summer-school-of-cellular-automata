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
