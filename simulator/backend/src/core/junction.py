"""
junction.py — junctions and turn routing (Stage 3).

A junction is a node where the *head* (exit) end of one or more incoming
roads meets the *tail* (entry) end of one or more outgoing roads. When a
vehicle reaches the exit of an incoming road it commits to one outgoing road,
chosen by configurable turn proportions (weighted random). The proportions
for each incoming road must sum to 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Junction:
    id: int
    x: float
    y: float
    # turns[incoming_road_id] = {outgoing_road_id: proportion}
    turns: dict[int, dict[int, float]] = field(default_factory=dict)

    def validate(self) -> None:
        """Every incoming road's outgoing proportions must sum to 1.0."""
        for in_road, outs in self.turns.items():
            if not outs:
                raise ValueError(f"junction {self.id}: incoming road {in_road} has no outgoing routes")
            total = sum(outs.values())
            if abs(total - 1.0) > 1e-9:
                raise ValueError(
                    f"junction {self.id}: turn proportions for incoming road "
                    f"{in_road} sum to {total}, must be 1.0"
                )
            if any(p < 0 for p in outs.values()):
                raise ValueError(f"junction {self.id}: negative proportion on road {in_road}")

    def choose_out(self, in_road_id: int, rng: np.random.Generator) -> int:
        """Weighted-random choice of an outgoing road for a vehicle from `in_road_id`."""
        outs = self.turns[in_road_id]
        roads = list(outs.keys())
        probs = np.array([outs[r] for r in roads], dtype=float)
        probs = probs / probs.sum()  # defensive renormalisation
        return int(rng.choice(roads, p=probs))

    def outgoing_for(self, in_road_id: int) -> list[int]:
        return list(self.turns.get(in_road_id, {}).keys())
