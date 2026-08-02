"""
test_disruptions.py — Stage 4 unified disruption mechanism tests.

Covers the behaviours stages.md requires: probability 0 never triggers,
probability 1 always triggers (where there is room), temporary disruptions
clear on schedule (repair), permanently-reserved cells never clear on their
own, a blocked cell actually blocks movement, and — critically — the Stage 1
flow-density baseline is bit-for-bit unperturbed when all disruptions are off.
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.rule184 import step as r184_step
from src.core.vehicle import Vehicle
from src.core.disruptions import DisruptionManager, STOCHASTIC_SPECS
from src.network.network import Network, Road
from src.network import grid_builder
from src.engine.simulation import Simulation


def _one_way_net(length=200, density=0.2, seed=1):
    net = grid_builder.build_one_way(length=length)
    net.populate_density(density, car_fraction=0.0, rng=np.random.default_rng(seed))
    return net


def test_probability_zero_never_triggers():
    net = _one_way_net()
    dm = DisruptionManager(net)
    dm.set_params(probs={k: 0.0 for k in STOCHASTIC_SPECS})
    rng = np.random.default_rng(0)
    for _ in range(500):
        dm.step(rng)
    assert dm.active == []


def test_probability_one_always_triggers():
    net = _one_way_net(density=0.1)  # plenty of room to place
    dm = DisruptionManager(net)
    dm.set_params(probs={"breakdown": 1.0})
    rng = np.random.default_rng(0)
    dm.step(rng)
    assert any(d.kind == "breakdown" for d in dm.active)


def test_temporary_disruption_clears_on_schedule():
    net = _one_way_net(density=0.05)
    dm = DisruptionManager(net)
    dm.set_params(probs={k: 0.0 for k in STOCHASTIC_SPECS})  # no new ones
    rng = np.random.default_rng(0)
    assert dm.trigger("breakdown", rng)
    d = dm.active[0]
    dur = d.remaining
    assert dur == STOCHASTIC_SPECS["breakdown"]["duration"]
    # advance exactly `dur` steps → repaired (removed)
    for _ in range(dur):
        dm.step(rng)
    assert all(x.kind != "breakdown" for x in dm.active)


def test_permanent_reservation_never_self_clears():
    net = _one_way_net(density=0.1)
    dm = DisruptionManager(net)
    dm.set_params(probs={k: 0.0 for k in STOCHASTIC_SPECS})
    rng = np.random.default_rng(0)
    assert dm.add_reserved("lock", rng)
    for _ in range(1000):
        dm.step(rng)
    assert any(d.kind == "lock" and d.permanent for d in dm.active)


def test_blocked_cell_blocks_movement():
    """A vehicle must not advance into a blocked cell (it queues)."""
    net = Network()
    net.add_road(Road(id=0, length=10, x0=0, y0=0, dx=1, dy=0, periodic=True))
    net.roads[0].vehicles = [Vehicle(id=1, front=3, length=1, vtype="moto")]
    net.blocked = {0: {4}}  # block the cell directly ahead
    rng = np.random.default_rng(0)
    net.step(rng)
    assert net.roads[0].vehicles[0].front == 3  # did not move into blocked cell
    # unblock → it advances next step
    net.blocked = {0: set()}
    net.step(rng)
    assert net.roads[0].vehicles[0].front == 4


def test_clear_removes_disruptions():
    net = _one_way_net(density=0.05)
    dm = DisruptionManager(net)
    rng = np.random.default_rng(0)
    dm.trigger("breakdown", rng)
    dm.add_reserved("lock", rng)
    assert len(dm.active) >= 1
    dm.clear("breakdown")
    assert all(d.kind != "breakdown" for d in dm.active)
    dm.clear()  # clear all
    assert dm.active == []


def test_stage1_baseline_unperturbed_when_all_off():
    """
    With no disruptions, the running Simulation is bit-for-bit identical to
    classic Rule 184 over many steps (the hard regression from plan.md §6).
    """
    sim = Simulation(config="one_way", length=300, density=0.35, seed=42)
    assert sim.disruptions.active == []
    arr = sim.roads[0].cells.copy()
    for _ in range(200):
        arr = r184_step(arr, periodic=True)
        sim.advance(1)
        assert np.array_equal(arr, sim.roads[0].cells)
    # blocked set must have stayed empty the entire time
    assert all(len(s) == 0 for s in sim.network.blocked.values())


def test_all_eight_terms_representable():
    """Every brief term maps onto a mechanism (Turn excluded as routing)."""
    kinds = set(STOCHASTIC_SPECS) | {"lock", "parking"}
    # breakdown, tree, accident, flood + lock, parking = 6 mechanisms covering
    # 7 brief terms (repair is the countdown, not a placeable kind); Turn is routing.
    assert {"breakdown", "tree", "accident", "flood", "lock", "parking"} <= kinds
