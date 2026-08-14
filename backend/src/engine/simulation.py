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
from src.core.vehicle import Vehicle
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
        lane_change_prob: float = 0.0,
        rear_safety_gap: int = 0,
        lane_change_require_gain: bool = True,
        build_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.length = length
        self.density_target = density
        self.car_fraction = car_fraction
        # lateral-transfer settings. Every one of these changes the outcome of
        # a step, so like every other such knob they persist across resets and
        # config switches, and round-trip through the scenario JSON.
        self.lane_change_prob = float(max(0.0, min(1.0, lane_change_prob)))
        self.rear_safety_gap = max(0, int(rear_safety_gap))
        self.lane_change_require_gain = bool(lane_change_require_gain)
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
        # structure snapshot for the "custom" config (map-edited/loaded networks)
        self._scenario_structure: dict[str, Any] | None = None
        self.network: Network = self._build()
        self.disruptions = DisruptionManager(self.network)
        self._apply_disruption_settings()

    # ------------------------------------------------------------------ build
    def _build(self) -> Network:
        from src.io.scenario_io import network_from_scenario

        if self.config == "custom" and self._scenario_structure is not None:
            # Rebuild the edited/loaded structure, then re-seed density.
            net = network_from_scenario(self._scenario_structure)
        else:
            kwargs = dict(self.build_kwargs)
            # `one_way` takes a `length`; others use their own geometry defaults.
            if self.config == "one_way":
                kwargs.setdefault("length", self.length)
            net = grid_builder.build(self.config, **kwargs)
        # Populate ring/parallel configs with an initial density; source-fed
        # (open) configs start empty and fill via their sources.
        if self._is_populatable(net):
            net.populate_density(self.density_target, self.car_fraction, self._rng)
        self._apply_lane_settings(net)
        return net

    # ------------------------------------------------------------- lane changing
    def _apply_lane_settings(self, net: Network | None = None) -> None:
        """Push the lateral-transfer settings onto a network."""
        net = self.network if net is None else net
        net.lane_change_prob = self.lane_change_prob
        net.rear_safety_gap = self.rear_safety_gap
        net.lane_change_require_gain = self.lane_change_require_gain

    def set_lane_change_params(
        self,
        prob: float | None = None,
        rear_gap: int | None = None,
        require_gain: bool | None = None,
    ) -> None:
        """Update any subset of the lateral settings; effective immediately."""
        if prob is not None:
            self.lane_change_prob = float(max(0.0, min(1.0, prob)))
        if rear_gap is not None:
            self.rear_safety_gap = max(0, int(rear_gap))
        if require_gain is not None:
            self.lane_change_require_gain = bool(require_gain)
        self._apply_lane_settings()

    def set_lane_change_prob(self, p: float) -> None:
        """Set P(lane change) for blocked vehicles; takes effect immediately."""
        self.set_lane_change_params(prob=p)

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
        lane_change_prob: float | None = None,
        rear_safety_gap: int | None = None,
        lane_change_require_gain: bool | None = None,
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
        if lane_change_prob is not None:
            self.lane_change_prob = float(max(0.0, min(1.0, lane_change_prob)))
        if rear_safety_gap is not None:
            self.rear_safety_gap = max(0, int(rear_safety_gap))
        if lane_change_require_gain is not None:
            self.lane_change_require_gain = bool(lane_change_require_gain)
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

    # ------------------------------------------------------------------ scenario I/O
    def to_scenario(self) -> dict[str, Any]:
        from src.io.scenario_io import save_scenario

        return save_scenario(self)

    def apply_scenario(self, data: dict[str, Any]) -> None:
        """Load a scenario in place, reproducing its exact state."""
        from src.io.scenario_io import network_from_scenario, restore_disruptions

        self.config = data.get("config", "custom")
        self.seed = int(data.get("seed", self.seed))
        self.density_target = float(data.get("density_target", self.density_target))
        self.car_fraction = float(data.get("car_fraction", self.car_fraction))
        self.lane_change_prob = float(
            data.get("lane_change_prob", self.lane_change_prob)
        )
        self.rear_safety_gap = int(data.get("rear_safety_gap", self.rear_safety_gap))
        self.lane_change_require_gain = bool(
            data.get("lane_change_require_gain", self.lane_change_require_gain)
        )
        self.steps_per_second = float(data.get("steps_per_second", self.steps_per_second))
        self.step_count = int(data.get("step", 0))
        self._last_moved = 0
        self._rng = np.random.default_rng(self.seed)
        if data.get("rng_state") is not None:
            # continue the exact stochastic stream from where it was saved
            self._rng.bit_generator.state = data["rng_state"]
        self.network = network_from_scenario(data)
        # remember the structure so a later reset rebuilds this exact layout
        self._scenario_structure = self._structure_snapshot()
        self.disruptions = DisruptionManager(self.network)
        restore_disruptions(self, data)

    def _structure_snapshot(self) -> dict[str, Any]:
        """Scenario-shaped dict of the current structure with empty vehicle lists."""
        snap = self.to_scenario()
        for r in snap["roads"]:
            r["vehicles"] = []
        snap["disruptions"] = {"probs": dict(self._disruption_probs),
                               "repair_scale": self._repair_scale, "active": []}
        return snap

    # ------------------------------------------------------------------ map editing
    def _mark_custom(self) -> None:
        """After a structural edit, switch to the custom config + snapshot."""
        self.config = "custom"
        self._scenario_structure = self._structure_snapshot()

    def add_road(self, x0: float, y0: float, dx: float, dy: float,
                 length: int, periodic: bool = False) -> int:
        new_id = (max(self.network.roads) + 1) if self.network.roads else 0
        self.network.add_road(Road(
            id=new_id, length=int(length), x0=float(x0), y0=float(y0),
            dx=float(dx), dy=float(dy), periodic=bool(periodic),
        ))
        self.network.blocked.setdefault(new_id, set())
        self._mark_custom()
        return new_id

    def remove_road(self, road_id: int) -> None:
        if road_id not in self.network.roads:
            return
        del self.network.roads[road_id]
        self.network.blocked.pop(road_id, None)
        # drop disruptions on that road and any junction turns referencing it
        self.disruptions.active = [d for d in self.disruptions.active if d.road_id != road_id]
        for j in self.network.junctions.values():
            j.turns.pop(road_id, None)
            for outs in j.turns.values():
                outs.pop(road_id, None)
        self.disruptions._publish()
        self._mark_custom()

    def add_vehicle(self, road_id: int, front: int, vtype: str = "moto") -> bool:
        road = self.network.roads.get(road_id)
        if road is None:
            return False
        from src.core.vehicle import FOOTPRINTS
        length = FOOTPRINTS.get(vtype, 1)
        occ = road.occupancy()
        cells = [(front - k) for k in range(length)]
        if any(c < 0 or c >= road.length or occ[c] for c in cells):
            return False
        road.vehicles.append(Vehicle(self.network.new_vid(), int(front), length, vtype))
        return True

    def remove_vehicle(self, road_id: int, cell: int) -> bool:
        road = self.network.roads.get(road_id)
        if road is None:
            return False
        for v in road.vehicles:
            if cell in v.cells(road.length, road.periodic):
                road.vehicles.remove(v)
                return True
        return False

    def set_turn(self, junction_id: int, in_road: int, proportions: dict[int, float]) -> bool:
        j = self.network.junctions.get(junction_id)
        if j is None:
            return False
        j.turns[int(in_road)] = {int(o): float(p) for o, p in proportions.items()}
        try:
            j.validate()
        except ValueError:
            return False
        self._mark_custom()
        return True

    # ------------------------------------------------------------------ region import (Stage 8)
    def import_region(self, place_name: str) -> dict[str, Any]:
        """
        Import a real-world road network from OSM for the given place name.

        Returns a status dict with keys:
            ok: bool, error: str|None, roads: int, junctions: int, total_cells: int
        """
        from src.mapdata.geocode import geocode
        from src.mapdata.overpass_client import fetch_roads
        from src.mapdata.osm_to_network import osm_to_network

        bbox = geocode(place_name)
        if bbox is None:
            return {"ok": False, "error": f"Could not geocode '{place_name}'"}

        south, west, north, east = bbox
        osm_data = fetch_roads(south, west, north, east)
        if osm_data is None:
            return {"ok": False, "error": "Overpass API request failed"}

        net = osm_to_network(
            osm_data,
            source_rate=0.3,
            car_fraction=self.car_fraction,
        )

        if not net.roads:
            return {"ok": False, "error": "No roads found in the specified region"}

        self.network = net
        self._apply_lane_settings(net)
        self.config = "custom"
        self.step_count = 0
        self._last_moved = 0
        self._rng = np.random.default_rng(self.seed)
        self._scenario_structure = self._structure_snapshot()
        self.disruptions = DisruptionManager(self.network)
        self._apply_disruption_settings()

        return {
            "ok": True,
            "error": None,
            "roads": len(net.roads),
            "junctions": len(net.junctions),
            "total_cells": sum(r.length for r in net.roads.values()),
        }


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

    def lane_changes(self) -> int:
        """Vehicles that shifted lane on the last step (lateral, not flow)."""
        return self.network.last_lane_changes

    def blocked_fraction(self) -> float:
        total = sum(r.length for r in self.network.roads.values())
        nblocked = sum(len(s) for s in self.network.blocked.values())
        return (nblocked / total) if total else 0.0

    def avg_queue_length(self) -> float:
        q = self.junction_queue_lengths()
        return (sum(q.values()) / len(q)) if q else 0.0

    def landscape(self) -> str:
        """Trivial / average / worst classification (Stage 6)."""
        from src.network.landscape import classify_landscape

        return classify_landscape(
            self.density(), self.blocked_fraction(), self.avg_queue_length()
        )

    # ------------------------------------------------------------------ misc
    def summary(self) -> dict[str, Any]:
        return {
            "step": self.step_count,
            "running": self.running,
            "steps_per_second": self.steps_per_second,
            "config": self.config,
            "n_roads": len(self.network.roads),
            "n_junctions": len(self.network.junctions),
            "n_streets": len(self.network.streets),
            "lane_change_prob": self.lane_change_prob,
            "rear_safety_gap": self.rear_safety_gap,
            "lane_change_require_gain": self.lane_change_require_gain,
            "density": self.density(),
            "flow": self.flow(),
        }
