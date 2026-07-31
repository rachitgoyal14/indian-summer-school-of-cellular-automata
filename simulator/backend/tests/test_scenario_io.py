"""
test_scenario_io.py — Stage 6 save/load round-trip tests.

The core guarantee: save → load → save yields an identical scenario dict, for
every configuration and after map edits and with disruptions active. Also that
a loaded simulation continues stepping identically to the original.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.engine.simulation import Simulation


def _roundtrip(sim: Simulation) -> None:
    data = sim.to_scenario()
    # must be JSON-serialisable
    text = json.dumps(data)
    reloaded = json.loads(text)
    sim2 = Simulation()
    sim2.apply_scenario(reloaded)
    again = sim2.to_scenario()
    assert again == data, "save→load→save is not identical"


def test_roundtrip_each_config():
    for cfg in ["one_way", "two_way_no_interaction", "two_way_turns",
                "two_way_bidirectional_turns", "grid"]:
        sim = Simulation(config=cfg, density=0.3, car_fraction=0.3, seed=1)
        for _ in range(30):
            sim.advance()
        _roundtrip(sim)


def test_roundtrip_with_disruptions():
    sim = Simulation(config="one_way", length=200, density=0.3, seed=2)
    sim.set_disruption_params(probs={"breakdown": 0.05, "accident": 0.05},
                              repair_scale=1.5)
    for _ in range(60):
        sim.advance()
    sim.add_reserved("lock")
    sim.add_reserved("parking")
    _roundtrip(sim)


def test_roundtrip_after_map_edits():
    sim = Simulation(config="one_way", length=100, density=0.2, seed=3)
    rid = sim.add_road(x0=0, y0=5, dx=1, dy=0, length=40, periodic=False)
    sim.add_vehicle(rid, 10, "car")
    sim.add_vehicle(rid, 20, "moto")
    assert sim.config == "custom"
    _roundtrip(sim)


def test_loaded_sim_steps_identically():
    sim = Simulation(config="grid", seed=5)
    for _ in range(40):
        sim.advance()
    data = sim.to_scenario()
    sim2 = Simulation()
    sim2.apply_scenario(json.loads(json.dumps(data)))
    # both advance with fresh RNGs seeded identically → identical evolution
    for _ in range(50):
        sim.advance()
        sim2.advance()
    occ1 = [r.occupancy().tolist() for r in sim.roads]
    occ2 = [r.occupancy().tolist() for r in sim2.roads]
    assert occ1 == occ2


def test_add_remove_vehicle_and_road():
    sim = Simulation(config="one_way", length=50, density=0.0, seed=7)
    assert sim.add_vehicle(0, 10, "moto")
    assert not sim.add_vehicle(0, 10, "moto")  # cell now occupied
    assert sim.remove_vehicle(0, 10)
    assert not sim.remove_vehicle(0, 10)       # nothing there now
    rid = sim.add_road(x0=0, y0=3, dx=1, dy=0, length=20)
    assert rid in sim.network.roads
    sim.remove_road(rid)
    assert rid not in sim.network.roads


def test_set_turn_validates():
    sim = Simulation(config="two_way_turns", seed=1)
    # road 0 → {1: 0.5, 2: 0.5} is valid
    assert sim.set_turn(0, 0, {1: 0.5, 2: 0.5})
    # invalid (sums to 0.8) is rejected
    assert not sim.set_turn(0, 0, {1: 0.5, 2: 0.3})
