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
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # type-only: `street` reaches this module through `network`
    from src.network.network import Road
    from src.network.street import Street


@dataclass
class Junction:
    id: int
    x: float
    y: float
    # turns[incoming_road_id] = {outgoing_road_id: proportion}
    turns: dict[int, dict[int, float]] = field(default_factory=dict)
    # lane_links[incoming_lane_road_id] = every outgoing lane it may reach.
    # Recorded when multi-lane streets are wired up (Stage 11) and carried
    # through save/load. v1 does NOT restrict turns by lane — `turns` above is
    # what the engine routes on — but keeping the full lane-to-lane graph is
    # what a later "outer lane may only turn left" rule would be built from.
    lane_links: dict[int, list[int]] = field(default_factory=dict)

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

    # ------------------------------------------------------------- streets
    def connect_road(self, road: "Road", end: str = "end") -> "Road":
        """
        Attach one road to this junction.

        `end="end"` means the road's *head* (its exit, cell `length-1`) feeds
        the junction; `end="start"` means its *tail* (cell 0) is fed by it.
        """
        if end not in ("start", "end"):
            raise ValueError(f"end must be 'start' or 'end', got {end!r}")
        if road.periodic:
            raise ValueError(
                f"junction {self.id}: road {road.id} is periodic (a ring) and "
                f"never reaches a junction; set periodic=False to connect it"
            )
        if end == "end":
            road.head_junction = self.id
        else:
            road.tail_junction = self.id
        return road

    def connect_street(
        self,
        street: "Street",
        end: str = "end",
        direction: str | None = None,
    ) -> list["Road"]:
        """
        Attach every lane of `street` to this junction, at `end`.

        A street meets a junction as a whole, so this is `connect_road` applied
        to each lane. Pass `direction` to attach only the lanes running one way
        — the usual case for a two-way street, whose forward lanes feed the
        junction ("end") while its backward lanes are fed by it ("start").

        Turn proportions are *not* invented here: `self.turns` still has to be
        filled in per incoming road, since only the caller knows the geometry.
        """
        lanes = (
            street.all_lanes() if direction is None
            else street.lanes_in_direction(direction)
        )
        return [self.connect_road(lane.road, end=end) for lane in lanes]
