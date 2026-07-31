"""
simulation.py — the live simulation model that the WebSocket server drives.

This is the stateful object that sits between the pure Stage 1 core
(`rule184.step`) and the network/serialization layer.  It is deliberately
structured around a *list of roads* even though Stage 2 only uses a single
road, so that Stage 3 (multiple roads + junctions) extends it rather than
rewrites it.

Design notes
------------
- The core movement rule is untouched Stage 1 code (`rule184.step`,
  `random_initial_state`).  This class only orchestrates *when* to step and
  keeps a snapshot of the previous state so instantaneous flow can be
  measured exactly (flow is defined from `state_before`, see
  analytics/density.py).
- `step_count` is a monotonically increasing integer.  The server stamps it
  into every outgoing message so the frontend can reject out-of-order /
  stale messages (Stage 2 desync requirement).
- Reset is seed-controllable so runs stay reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.core.cell import random_initial_state
from src.core.rule184 import step as rule184_step
from src.analytics.density import density_of, flow_at_step


@dataclass
class Road:
    """
    One 1D Rule 184 lane plus the 2D geometry used to lay it out in the
    frontend.  Geometry is a straight segment: cell k is drawn at
    (x0 + k*dx, y0 + k*dy).  Stage 2 uses a single horizontal road; Stage 3
    reuses the same structure for arbitrarily placed segments.
    """

    id: int
    cells: np.ndarray                     # int8: 0 = empty, 1 = vehicle (Stage 2)
    x0: float = 0.0
    y0: float = 0.0
    dx: float = 1.0
    dy: float = 0.0
    periodic: bool = True
    # snapshot of the previous tick, for exact flow measurement
    prev_cells: np.ndarray | None = None

    @property
    def length(self) -> int:
        return len(self.cells)

    def geometry(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "dx": self.dx, "dy": self.dy}


class Simulation:
    """
    A running Rule 184 simulation over one or more roads.

    Stage 2: a single periodic road.  Public API (`advance`, `pause`,
    `resume`, `single_step`, `reset`, `set_speed`) is what the WebSocket
    server calls in response to control messages.
    """

    def __init__(
        self,
        length: int = 500,
        density: float = 0.30,
        seed: int = 42,
        periodic: bool = True,
        steps_per_second: float = 12.0,
    ) -> None:
        self.length = length
        self.density_target = density
        self.seed = seed
        self.periodic = periodic
        self.steps_per_second = steps_per_second

        self.running = True
        self.step_count = 0
        self._rng = np.random.default_rng(seed)

        self.roads: list[Road] = []
        self._build_initial_road(length, density)

    # ------------------------------------------------------------------ build
    def _build_initial_road(self, length: int, density: float) -> None:
        cells = random_initial_state(length, density, self._rng)
        road = Road(
            id=0,
            cells=cells,
            x0=0.0,
            y0=0.0,
            dx=1.0,
            dy=0.0,
            periodic=self.periodic,
            prev_cells=cells.copy(),
        )
        self.roads = [road]

    # ------------------------------------------------------------------ ticking
    def advance(self, n: int = 1) -> None:
        """Advance the simulation by `n` synchronous Rule 184 steps."""
        for _ in range(n):
            for road in self.roads:
                road.prev_cells = road.cells
                road.cells = rule184_step(road.cells, periodic=road.periodic)
            self.step_count += 1

    def single_step(self) -> None:
        """Advance exactly one step regardless of running/paused state."""
        self.advance(1)

    def pause(self) -> None:
        self.running = False

    def resume(self) -> None:
        self.running = True

    def set_speed(self, steps_per_second: float) -> None:
        # clamp to a sane range so the async loop never busy-spins or stalls
        self.steps_per_second = float(max(0.5, min(120.0, steps_per_second)))

    def reset(
        self,
        density: float | None = None,
        seed: int | None = None,
        length: int | None = None,
    ) -> None:
        """Rebuild the initial state.  Keeps the sim reproducible."""
        if density is not None:
            self.density_target = float(max(0.0, min(1.0, density)))
        if seed is not None:
            self.seed = int(seed)
        if length is not None:
            self.length = int(length)
        self._rng = np.random.default_rng(self.seed)
        self.step_count = 0
        self._build_initial_road(self.length, self.density_target)

    # ------------------------------------------------------------------ analytics
    def density(self) -> float:
        """Network-wide density (occupied cells / total cells)."""
        total = sum(int(r.cells.sum()) for r in self.roads)
        cells = sum(r.length for r in self.roads)
        return total / cells if cells else 0.0

    def flow(self) -> float:
        """
        Network-wide instantaneous flow, averaged over roads weighted by
        length.  Uses the previous-tick snapshot, so it reports the flow
        that actually occurred on the most recent step.
        """
        num = 0.0
        den = 0
        for r in self.roads:
            before = r.prev_cells if r.prev_cells is not None else r.cells
            num += flow_at_step(before, r.cells) * r.length
            den += r.length
        return num / den if den else 0.0

    # ------------------------------------------------------------------ misc
    def summary(self) -> dict[str, Any]:
        return {
            "step": self.step_count,
            "running": self.running,
            "steps_per_second": self.steps_per_second,
            "n_roads": len(self.roads),
            "density": self.density(),
            "flow": self.flow(),
        }
