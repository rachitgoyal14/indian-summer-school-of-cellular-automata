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
from src.core.disruptions import DisruptionManager


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
        # disruption settings persist across resets/config switches
        self._disruption_probs: dict[str, float] = {}
        self._repair_scale: float = 1.0
        self.network: Network = self._build()
        self.disruptions = DisruptionManager(self.network)
        self._apply_disruption_settings()

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
            # update disruptions (repair countdown + probabilistic triggers),
            # then advance the traffic on the resulting blocked layout.
            self.disruptions.step(self._rng)
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
        # rebuild disruptions for the new network, preserving the user's
        # probability / repair-speed settings (but clearing placed instances).
        self.disruptions = DisruptionManager(self.network)
        self._apply_disruption_settings()

    def load_config(self, config: str, **build_kwargs: Any) -> None:
        """Switch to a different lane/junction configuration and rebuild."""
        self.config = config
        self.build_kwargs = build_kwargs
        self.reset()

    # ------------------------------------------------------------------ disruptions
    def _apply_disruption_settings(self) -> None:
        self.disruptions.set_params(
            probs=self._disruption_probs, repair_scale=self._repair_scale
        )

    def set_disruption_params(
        self,
        probs: dict[str, float] | None = None,
        repair_scale: float | None = None,
    ) -> None:
        if probs:
            self._disruption_probs.update({k: float(v) for k, v in probs.items()})
        if repair_scale is not None:
            self._repair_scale = float(repair_scale)
        self._apply_disruption_settings()

    def trigger_disruption(self, kind: str) -> bool:
        return self.disruptions.trigger(kind, self._rng)

    def add_reserved(self, kind: str) -> bool:
        return self.disruptions.add_reserved(kind, self._rng)

    def clear_disruptions(self, kind: str | None = None) -> None:
        self.disruptions.clear(kind)

    # ------------------------------------------------------------------ analytics
    def density(self) -> float:
        return self.network.density()

    def entropy(self, window_size: int = 10) -> tuple[float, float]:
        """(bits, normalised) Shannon entropy of the vehicle spatial spread."""
        from src.analytics.entropy import network_entropy

        occs = [r.occupancy() for r in self.network.roads.values()]
        return network_entropy(occs, window_size=window_size)

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
