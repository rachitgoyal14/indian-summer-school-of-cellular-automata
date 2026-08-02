"""
footprint.py — footprint-aware synchronous movement for a single road.

This generalises Rule 184 to multi-cell vehicles while keeping the exact
Rule 184 semantics for 1-cell vehicles (the Stage 1 regression target).

The movement rule, per plan.md §5:
    a vehicle's front advances by one cell iff the single cell immediately
    ahead of its front is empty in the *previous* (snapshot) occupancy.

Key correctness facts (all covered by tests):
- For all-motorbike (length 1) roads, this is identical, tick-for-tick, to
  `rule184.step` (both periodic and, with draining, open boundaries).
- The check uses the whole *footprint* occupancy: a car body cell counts as
  occupied for the vehicle behind it, so no vehicle ever advances into any
  cell of a multi-cell vehicle.
- Synchronous: every decision is read from one immutable snapshot, so the
  update is order-independent and collision-free (distinct vehicles always
  target distinct cells — their fronts differ by ≥1).
"""

from __future__ import annotations

import numpy as np

from src.core.vehicle import Vehicle


def build_occupancy(
    vehicles: list[Vehicle], length: int, periodic: bool
) -> np.ndarray:
    """Derive the 0/1 occupancy array from a vehicle list (single source of truth)."""
    occ = np.zeros(length, dtype=np.int8)
    for v in vehicles:
        for c in v.cells(length, periodic):
            occ[c] = 1
    return occ


def vehicles_from_occupancy(occ: np.ndarray) -> list[Vehicle]:
    """One motorbike (length 1) per occupied cell — for Rule 184 equivalence tests."""
    return [
        Vehicle(id=i, front=int(i), length=1, vtype="moto")
        for i, v in enumerate(occ)
        if v
    ]


def step_single_road(
    vehicles: list[Vehicle],
    length: int,
    periodic: bool,
) -> tuple[list[Vehicle], int]:
    """
    One synchronous footprint-aware step on a single road.

    Returns (new_vehicles, moved_count). On an open (non-periodic) road a
    vehicle whose front would advance past the last cell exits the road
    (is dropped) — this drains an open lane; the network layer replaces this
    with junction routing where roads connect.
    """
    occ = build_occupancy(vehicles, length, periodic)
    new_vehicles: list[Vehicle] = []
    moved = 0
    for v in vehicles:
        nxt = v.front + 1
        if nxt >= length:
            if periodic:
                nxt_wrapped = nxt % length
                if occ[nxt_wrapped] == 0:
                    new_vehicles.append(
                        Vehicle(v.id, nxt_wrapped, v.length, v.vtype)
                    )
                    moved += 1
                else:
                    new_vehicles.append(v)
            else:
                # open boundary: front runs off the end → vehicle exits.
                moved += 1
                continue
        else:
            if occ[nxt] == 0:
                new_vehicles.append(Vehicle(v.id, nxt, v.length, v.vtype))
                moved += 1
            else:
                new_vehicles.append(v)
    return new_vehicles, moved
