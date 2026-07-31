"""
test_footprint.py — Stage 3 footprint-aware movement tests.

The most important test here is `test_equivalent_to_rule184_periodic`: it
proves the new agent/footprint engine is tick-for-tick identical to the
Stage 1 `rule184.step` when every vehicle is a single cell. That is what lets
the network layer be built on this engine without endangering the Stage 1
mathematical baseline.
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
from src.core.footprint import (
    build_occupancy,
    vehicles_from_occupancy,
    step_single_road,
)


# ===========================================================================
# Rule 184 equivalence (the regression guarantee for the new engine)
# ===========================================================================

def test_equivalent_to_rule184_periodic():
    """All-motorbike footprint stepping == classic Rule 184, over many steps/seeds."""
    L = 200
    for seed in (1, 42, 7777, 12345):
        rng = np.random.default_rng(seed)
        for density in (0.1, 0.3, 0.5, 0.7, 0.9):
            n = round(density * L)
            occ = np.zeros(L, dtype=np.int8)
            occ[rng.choice(L, size=n, replace=False)] = 1

            arr = occ.copy()
            vehicles = vehicles_from_occupancy(occ)

            for _ in range(120):
                arr = r184_step(arr, periodic=True)
                vehicles, _ = step_single_road(vehicles, L, periodic=True)
                derived = build_occupancy(vehicles, L, periodic=True)
                assert np.array_equal(arr, derived), (
                    f"divergence seed={seed} density={density}"
                )


# ===========================================================================
# Footprint correctness (car occupies its whole footprint)
# ===========================================================================

def test_car_occupies_full_footprint():
    car = Vehicle(id=0, front=5, length=2, vtype="car")
    occ = build_occupancy([car], length=10, periodic=False)
    # car of length 2 with front at 5 occupies cells {4, 5}
    assert occ[4] == 1 and occ[5] == 1
    assert occ.sum() == 2


def test_follower_cannot_enter_car_body():
    """A motorbike directly behind a car's body cell must NOT advance into it."""
    # car occupies {4,5}; motorbike front at 3 (cell ahead = 4 = car body)
    car = Vehicle(id=0, front=5, length=2, vtype="car")
    moto = Vehicle(id=1, front=3, length=1, vtype="moto")
    L = 20
    vehicles, moved = step_single_road([car, moto], L, periodic=False)
    by_id = {v.id: v for v in vehicles}
    # car had a free cell ahead (6) so it advanced; motorbike was blocked by
    # the car's *body* cell (4), proving footprint-aware blocking.
    assert by_id[0].front == 6            # car advanced
    assert by_id[1].front == 3            # motorbike blocked, did not move
    assert moved == 1


def test_car_moves_as_a_unit():
    car = Vehicle(id=0, front=5, length=2, vtype="car")
    L = 20
    vehicles, moved = step_single_road([car], L, periodic=False)
    v = vehicles[0]
    assert v.front == 6 and v.tail == 5   # whole footprint shifted by exactly 1
    assert moved == 1


def test_no_overlap_after_mixed_steps():
    """Mixed motos/cars: after many steps, occupancy never exceeds sum of footprints."""
    L = 80
    rng = np.random.default_rng(3)
    # place a few non-overlapping vehicles by scanning
    vehicles: list[Vehicle] = []
    occ = np.zeros(L, dtype=np.int8)
    vid = 0
    for front in rng.permutation(L):
        length = 2 if rng.random() < 0.4 else 1
        cells = [(front - k) % L for k in range(length)]
        if any(occ[c] for c in cells):
            continue
        for c in cells:
            occ[c] = 1
        vehicles.append(Vehicle(vid, int(front), length, "car" if length == 2 else "moto"))
        vid += 1
        if len(vehicles) >= 20:
            break

    total_footprint = sum(v.length for v in vehicles)
    for _ in range(300):
        vehicles, _ = step_single_road(vehicles, L, periodic=True)
        occ = build_occupancy(vehicles, L, periodic=True)
        # no cell double-booked → sum of occupancy equals total footprint
        assert int(occ.sum()) == total_footprint


def test_open_road_drains():
    """On an open road with no source, all vehicles eventually exit."""
    L = 30
    vehicles = [Vehicle(i, front=i, length=1, vtype="moto") for i in range(5)]
    for _ in range(L + 10):
        vehicles, _ = step_single_road(vehicles, L, periodic=False)
    assert vehicles == []
