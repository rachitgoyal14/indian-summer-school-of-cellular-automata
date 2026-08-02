"""
disruptions.py — the unified disruption ("liberty degree") mechanism (Stage 4).

Per plan.md §4, all 8 brief-listed disruptions share just THREE underlying
mechanisms; we do not build 8 independent systems:

  A. temporarily-blocked single cell   (auto-clears after a countdown)
  B. temporarily-blocked multi-cell     (a segment; auto-clears)
  C. permanently-reserved cell(s)       (only clears on explicit user action)

plus a repair/countdown clearing rule that is always active on A and B.

Brief term        → mechanism → trigger
-----------------------------------------------------------------------------
Fall car (breakdown) → A (1 cell)        → probability per step
Fallen tree          → A (1 cell)        → probability per step (same mechanism,
                                            distinct label/colour)
Accident (two cars)  → B (2 adj. cells)  → probability per step
Flood                → B (segment)       → probability per step OR manual
Repair               → the countdown that clears A/B → always active
Locks/gears          → C (1 cell)        → manual toggle
Parking              → C (edge cell)     → manual toggle
Turn                 → NOT a disruption (ordinary junction routing, Stage 3)

A blocked cell is treated as *occupied* by the movement rule: no vehicle may
enter it, so traffic queues behind it (which is the whole point). When all
disruptions are off the blocked set is empty and the engine is bit-for-bit
the Stage 1 Rule 184 baseline (regression-tested).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Stochastic, temporary disruptions: (mechanism A/B). `size` cells, `duration`
# base steps until repair, `permanent` False.
STOCHASTIC_SPECS: dict[str, dict] = {
    "breakdown": {"label": "Fall car (breakdown)", "size": 1, "duration": 45},
    "tree":      {"label": "Fallen tree",          "size": 1, "duration": 55},
    "accident":  {"label": "Accident (two cars)",  "size": 2, "duration": 70},
    "flood":     {"label": "Flood",                "size": 10, "duration": 130},
}

# Permanent, manually toggled reservations (mechanism C).
RESERVED_SPECS: dict[str, dict] = {
    "lock":    {"label": "Locks/gears", "edge": False},
    "parking": {"label": "Parking",     "edge": True},
}

ALL_KINDS = list(STOCHASTIC_SPECS) + list(RESERVED_SPECS)


@dataclass
class Disruption:
    id: int
    kind: str
    label: str
    road_id: int
    cells: list[int]
    permanent: bool
    remaining: int = 0  # steps until auto-repair (temp only)


class DisruptionManager:
    """
    Owns the active disruptions for a `Network`, applies the repair countdown,
    fires probability-driven disruptions, and republishes the network's
    `blocked` cell sets each step.
    """

    def __init__(self, network) -> None:
        self.net = network
        self.next_id = 1
        self.active: list[Disruption] = []
        # per-step trigger probability for each stochastic kind (0 = off)
        self.probs: dict[str, float] = {k: 0.0 for k in STOCHASTIC_SPECS}
        # duration multiplier — the "Repair speed" control (lower = faster repair)
        self.repair_scale: float = 1.0
        self._publish()

    # --------------------------------------------------------------- config
    def set_params(
        self,
        probs: dict[str, float] | None = None,
        repair_scale: float | None = None,
    ) -> None:
        if probs:
            for k, v in probs.items():
                if k in self.probs:
                    self.probs[k] = float(max(0.0, min(1.0, v)))
        if repair_scale is not None:
            self.repair_scale = float(max(0.1, min(3.0, repair_scale)))

    # --------------------------------------------------------------- ticking
    def step(self, rng: np.random.Generator) -> None:
        # 1. repair countdown clears temporary blockages on schedule
        for d in self.active:
            if not d.permanent:
                d.remaining -= 1
        self.active = [d for d in self.active if d.permanent or d.remaining > 0]

        # 2. probability-driven triggers
        for kind, p in self.probs.items():
            if p > 0.0 and rng.random() < p:
                self._place_stochastic(kind, rng)

        self._publish()

    # --------------------------------------------------------------- manual
    def trigger(self, kind: str, rng: np.random.Generator) -> bool:
        """Manually place one stochastic disruption now (e.g. 'flood now')."""
        ok = False
        if kind in STOCHASTIC_SPECS:
            ok = self._place_stochastic(kind, rng)
        self._publish()
        return ok

    def add_reserved(self, kind: str, rng: np.random.Generator) -> bool:
        if kind not in RESERVED_SPECS:
            return False
        spec = RESERVED_SPECS[kind]
        road = self._pick_road(rng)
        if road is None:
            return False
        occ = road.occupancy()
        blocked = self.net.blocked.get(road.id, set())
        # parking sits near an edge; locks may be anywhere free
        candidates = (
            list(range(0, min(6, road.length))) + list(range(max(0, road.length - 6), road.length))
            if spec["edge"]
            else list(range(road.length))
        )
        rng.shuffle(candidates)
        for c in candidates:
            if occ[c] == 0 and c not in blocked:
                self.active.append(Disruption(
                    id=self._new_id(), kind=kind, label=spec["label"],
                    road_id=road.id, cells=[int(c)], permanent=True,
                ))
                self._publish()
                return True
        return False

    def clear(self, kind: str | None = None) -> None:
        if kind is None:
            self.active = []
        else:
            self.active = [d for d in self.active if d.kind != kind]
        self._publish()

    # --------------------------------------------------------------- placement
    def _place_stochastic(self, kind: str, rng: np.random.Generator) -> bool:
        spec = STOCHASTIC_SPECS[kind]
        size = spec["size"]
        road = self._pick_road(rng)
        if road is None or size > road.length:
            return False
        occ = road.occupancy()
        blocked = self.net.blocked.get(road.id, set())
        # try a bounded number of random contiguous windows that are fully free
        for _ in range(24):
            start = int(rng.integers(0, road.length - size + 1))
            window = list(range(start, start + size))
            if all(occ[c] == 0 and c not in blocked for c in window):
                duration = max(1, int(round(spec["duration"] * self.repair_scale)))
                self.active.append(Disruption(
                    id=self._new_id(), kind=kind, label=spec["label"],
                    road_id=road.id, cells=[int(c) for c in window],
                    permanent=False, remaining=duration,
                ))
                return True
        return False

    def _pick_road(self, rng: np.random.Generator):
        roads = self.net.roads_ordered()
        if not roads:
            return None
        # weight by length so longer roads are proportionally more likely
        weights = np.array([r.length for r in roads], dtype=float)
        weights /= weights.sum()
        return roads[int(rng.choice(len(roads), p=weights))]

    def _new_id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i

    # --------------------------------------------------------------- publish
    def _publish(self) -> None:
        blocked: dict[int, set[int]] = {rid: set() for rid in self.net.roads}
        for d in self.active:
            blocked.setdefault(d.road_id, set()).update(d.cells)
        self.net.blocked = blocked

    # --------------------------------------------------------------- view
    def to_list(self) -> list[dict]:
        return [
            {
                "id": d.id,
                "kind": d.kind,
                "label": d.label,
                "road_id": d.road_id,
                "cells": d.cells,
                "permanent": d.permanent,
                "remaining": d.remaining,
            }
            for d in self.active
        ]
