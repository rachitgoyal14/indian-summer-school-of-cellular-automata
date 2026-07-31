"""
simulation.py — the live simulation model that the WebSocket server drives.

As of Stage 3 this wraps a `Network` (one or more roads connected at
junctions, footprint-aware vehicles). The default configuration is a single
one-way periodic ring (the Stage 1/2 baseline), so existing behaviour and
tests are preserved; other configurations are selected via `config`.

Public API used by the server (`advance`, `pause`, `resume`, `single_step`,
`reset`, `set_speed`, `load_config`) is unchanged from Stage 2 in spirit.
`self.roads` exposes the network's roads; each `Road.cells` is its occupancy
grid, so Stage 2 code/tests that read `sim.roads[0].cells` keep working.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.network import grid_builder
from src.network.network import Network, Road


class Simulation:
    def __init__(
        self,
        config: str = "one_way",
        length: int = 500,
        density: float = 0.30,
        seed: int = 42,
        steps_per_second: float = 12.0,
        car_fraction: float = 0.0,
        build_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.length = length
        self.density_target = density
        self.car_fraction = car_fraction
        self.seed = seed
        self.steps_per_second = steps_per_second
        self.build_kwargs = build_kwargs or {}

        self.running = True
        self.step_count = 0
        self._last_moved = 0
        self._rng = np.random.default_rng(seed)
        self.network: Network = self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> Network:
        kwargs = dict(self.build_kwargs)
        # `one_way` takes a `length`; the others use their own geometry defaults.
        if self.config == "one_way":
            kwargs.setdefault("length", self.length)
        net = grid_builder.build(self.config, **kwargs)
        # Populate ring/parallel configs with an initial density; source-fed
        # (open) configs start empty and fill via their sources.
        if self._is_populatable(net):
            net.populate_density(self.density_target, self.car_fraction, self._rng)
        return net

    @staticmethod
    def _is_populatable(net: Network) -> bool:
        # Only pre-seed roads that are periodic (rings); open roads fill from sources.
        return any(r.periodic for r in net.roads.values())

    # ------------------------------------------------------------------ access
    @property
    def roads(self) -> list[Road]:
        return self.network.roads_ordered()

    # ------------------------------------------------------------------ ticking
    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            self._last_moved = self.network.step(self._rng)
            self.step_count += 1

    def single_step(self) -> None:
        self.advance(1)

    def pause(self) -> None:
        self.running = False

    def resume(self) -> None:
        self.running = True

    def set_speed(self, steps_per_second: float) -> None:
        self.steps_per_second = float(max(0.5, min(120.0, steps_per_second)))

    def reset(
        self,
        density: float | None = None,
        seed: int | None = None,
        length: int | None = None,
        car_fraction: float | None = None,
        config: str | None = None,
    ) -> None:
        if density is not None:
            self.density_target = float(max(0.0, min(1.0, density)))
        if seed is not None:
            self.seed = int(seed)
        if length is not None:
            self.length = int(length)
        if car_fraction is not None:
            self.car_fraction = float(max(0.0, min(1.0, car_fraction)))
        if config is not None:
            self.config = config
        self._rng = np.random.default_rng(self.seed)
        self.step_count = 0
        self._last_moved = 0
        self.network = self._build()

    def load_config(self, config: str, **build_kwargs: Any) -> None:
        """Switch to a different lane/junction configuration and rebuild."""
        self.config = config
        self.build_kwargs = build_kwargs
        self.reset()

    # ------------------------------------------------------------------ analytics
    def density(self) -> float:
        return self.network.density()

    def flow(self) -> float:
        """Vehicles that advanced last step / total cells (veh/cell/step)."""
        total = sum(r.length for r in self.network.roads.values())
        return (self._last_moved / total) if total else 0.0

    def junction_queue_lengths(self) -> dict[int, int]:
        return self.network.junction_queue_lengths()

    # ------------------------------------------------------------------ misc
    def summary(self) -> dict[str, Any]:
        return {
            "step": self.step_count,
            "running": self.running,
            "steps_per_second": self.steps_per_second,
            "config": self.config,
            "n_roads": len(self.network.roads),
            "n_junctions": len(self.network.junctions),
            "density": self.density(),
            "flow": self.flow(),
        }
