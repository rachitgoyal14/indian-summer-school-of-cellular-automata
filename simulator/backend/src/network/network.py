"""
network.py — a network of Rule 184 roads connected at junctions.

This is the engine that runs in the app from Stage 3 on. It generalises the
single periodic road (Stage 1/2) to:
  - multiple roads with 2D geometry,
  - heterogeneous vehicle footprints (motorbike/car),
  - junctions with weighted turn routing,
  - open roads with sources (inflow) and sinks (outflow).

It preserves the Stage 1 baseline exactly: a single periodic road of
motorbikes steps identically to `rule184.step` (see test_network.py).

Synchronous update (collision-free by construction)
---------------------------------------------------
Every step is resolved from one immutable occupancy snapshot, in ordered
passes against a *projected* new occupancy so no two vehicles ever land on
the same cell:

  Pass A  intra-road moves / stays / periodic wrap / sink exit
  Pass B  junction transfers (claim entry cells on the projected grid;
          blocked vehicles queue in place — this is the congestion backup)
  Pass C  sources spawn at open road entries when there is room

The movement rule itself is the footprint-aware Rule 184 rule: a vehicle's
front advances one cell iff the cell ahead is empty in the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.core.vehicle import Vehicle, FOOTPRINTS
from src.core.junction import Junction

# how many cells back from an incoming road's exit count as "in the queue"
QUEUE_WINDOW = 12


@dataclass
class Road:
    id: int
    length: int
    x0: float = 0.0
    y0: float = 0.0
    dx: float = 1.0
    dy: float = 0.0
    periodic: bool = True
    head_junction: int | None = None   # exit (index length-1) feeds this junction
    tail_junction: int | None = None   # entry (index 0) is fed by this junction
    source_rate: float = 0.0           # P(spawn) per step at the entry (open tail)
    source_car_fraction: float = 0.0
    vehicles: list[Vehicle] = field(default_factory=list)

    def occupancy(self) -> np.ndarray:
        occ = np.zeros(self.length, dtype=np.int8)
        for v in self.vehicles:
            for c in v.cells(self.length, self.periodic):
                occ[c] = 1
        return occ

    # Stage 2 compatibility: `.cells` is the occupancy grid.
    @property
    def cells(self) -> np.ndarray:
        return self.occupancy()

    def geometry(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "dx": self.dx, "dy": self.dy}


class Network:
    def __init__(self) -> None:
        self.roads: dict[int, Road] = {}
        self.junctions: dict[int, Junction] = {}
        self._vid = 0  # global vehicle id counter
        # cells made unavailable by disruptions (Stage 4). Empty by default,
        # so with no disruptions the engine is the exact Rule 184 baseline.
        self.blocked: dict[int, set[int]] = {}

    # ------------------------------------------------------------- building
    def add_road(self, road: Road) -> Road:
        self.roads[road.id] = road
        return road

    def add_junction(self, j: Junction) -> Junction:
        self.junctions[j.id] = j
        return j

    def validate(self) -> None:
        for j in self.junctions.values():
            j.validate()

    def new_vid(self) -> int:
        self._vid += 1
        return self._vid

    def all_vehicles(self) -> list[Vehicle]:
        return [v for r in self.roads.values() for v in r.vehicles]

    def roads_ordered(self) -> list[Road]:
        return [self.roads[k] for k in sorted(self.roads)]

    # ------------------------------------------------------------- placement
    def populate_density(
        self,
        density: float,
        car_fraction: float,
        rng: np.random.Generator,
    ) -> None:
        """
        Place non-overlapping vehicles on every road to ~target density.

        For car_fraction == 0 the placement is *exactly* the Stage 1 method
        (one motorbike per chosen cell, exact integer count) so a single
        periodic road reproduces the Stage 1 initial condition bit-for-bit.
        """
        for road in self.roads_ordered():
            road.vehicles = []
            if car_fraction <= 0.0:
                n = round(density * road.length)
                n = min(n, road.length)
                chosen = rng.choice(road.length, size=n, replace=False)
                for c in sorted(chosen):
                    road.vehicles.append(
                        Vehicle(self.new_vid(), int(c), 1, "moto")
                    )
                continue

            # mixed vehicles: greedy non-overlapping placement toward density
            occ = np.zeros(road.length, dtype=np.int8)
            target = int(density * road.length)
            placed = 0
            for front in rng.permutation(road.length):
                if placed >= target:
                    break
                is_car = rng.random() < car_fraction
                length = FOOTPRINTS["car"] if is_car else FOOTPRINTS["moto"]
                cells = [(int(front) - k) for k in range(length)]
                if any(c < 0 or occ[c] for c in cells):
                    continue
                for c in cells:
                    occ[c] = 1
                road.vehicles.append(
                    Vehicle(self.new_vid(), int(front), length,
                            "car" if is_car else "moto")
                )
                placed += length

    # ------------------------------------------------------------- stepping
    def step(self, rng: np.random.Generator) -> int:
        """Advance one synchronous step. Returns the number of vehicles that moved."""
        occ_old = {rid: r.occupancy() for rid, r in self.roads.items()}
        # projected new occupancy, filled as we resolve movement
        occ_new = {rid: np.zeros(r.length, dtype=np.int8) for rid, r in self.roads.items()}
        new_lists: dict[int, list[Vehicle]] = {rid: [] for rid in self.roads}
        transfer_pending: list[tuple[int, Vehicle]] = []  # (road_id, vehicle)
        moved = 0

        # disrupted cells behave like occupied cells: nothing may enter them.
        blk = self.blocked

        def free(rid: int, cell: int) -> bool:
            return occ_old[rid][cell] == 0 and cell not in blk.get(rid, ())

        # ---- Pass A: intra-road resolution ----
        for rid, road in self.roads.items():
            L = road.length
            for v in road.vehicles:
                nxt = v.front + 1
                if nxt < L:
                    if free(rid, nxt):
                        nv = Vehicle(v.id, nxt, v.length, v.vtype)
                        _place(occ_new[rid], nv, L, road.periodic)
                        new_lists[rid].append(nv)
                        moved += 1
                    else:
                        _place(occ_new[rid], v, L, road.periodic)
                        new_lists[rid].append(v)
                else:
                    # front at last cell -> exit behaviour
                    if road.periodic:
                        w = nxt % L
                        if free(rid, w):
                            nv = Vehicle(v.id, w, v.length, v.vtype)
                            _place(occ_new[rid], nv, L, road.periodic)
                            new_lists[rid].append(nv)
                            moved += 1
                        else:
                            _place(occ_new[rid], v, L, road.periodic)
                            new_lists[rid].append(v)
                    elif road.head_junction is not None:
                        # defer; keep occupying its current cells until resolved
                        _place(occ_new[rid], v, L, road.periodic)
                        new_lists[rid].append(v)
                        transfer_pending.append((rid, v))
                    else:
                        # sink: vehicle leaves the network
                        moved += 1

        # ---- Pass B: junction transfers ----
        # deterministic order: by road id then front, so results are reproducible
        transfer_pending.sort(key=lambda t: (t[0], t[1].front))
        for rid, v in transfer_pending:
            road = self.roads[rid]
            j = self.junctions.get(road.head_junction)
            if j is None or rid not in j.turns:
                continue
            out_id = j.choose_out(rid, rng)
            out = self.roads[out_id]
            entry = list(range(v.length))  # cells [0 .. length-1]
            if any(c >= out.length for c in entry):
                continue
            out_blk = blk.get(out_id, ())
            if all(occ_new[out_id][c] == 0 and c not in out_blk for c in entry):
                # remove from current road (free its old cells in projection)
                new_lists[rid].remove(v)
                _unplace(occ_new[rid], v, road.length, road.periodic)
                nv = Vehicle(v.id, v.length - 1, v.length, v.vtype)
                for c in entry:
                    occ_new[out_id][c] = 1
                new_lists[out_id].append(nv)
                moved += 1
            # else: blocked -> stays in place (already in new_lists[rid]) = queue

        # ---- Pass C: sources ----
        # A source spawns at an open tail (index 0) that is not fed by a junction.
        for rid, road in self.roads.items():
            if road.source_rate <= 0.0 or road.tail_junction is not None:
                continue
            if rng.random() < road.source_rate:
                is_car = rng.random() < road.source_car_fraction
                length = FOOTPRINTS["car"] if is_car else FOOTPRINTS["moto"]
                entry = list(range(length))
                road_blk = blk.get(rid, ())
                if length <= road.length and all(
                    occ_new[rid][c] == 0 and c not in road_blk for c in entry
                ):
                    for c in entry:
                        occ_new[rid][c] = 1
                    new_lists[rid].append(
                        Vehicle(self.new_vid(), length - 1, length,
                                "car" if is_car else "moto")
                    )

        for rid in self.roads:
            self.roads[rid].vehicles = new_lists[rid]
        return moved

    # ------------------------------------------------------------- metrics
    def density(self) -> float:
        total = sum(int(r.occupancy().sum()) for r in self.roads.values())
        cells = sum(r.length for r in self.roads.values())
        return total / cells if cells else 0.0

    def junction_queue_lengths(self) -> dict[int, int]:
        """
        Per-junction backup: number of vehicles sitting within QUEUE_WINDOW
        cells of the exit on any road feeding that junction. Camera-independent
        readout used to observe congestion propagation.
        """
        q: dict[int, int] = {jid: 0 for jid in self.junctions}
        for road in self.roads.values():
            if road.head_junction is None:
                continue
            threshold = road.length - QUEUE_WINDOW
            n = sum(1 for v in road.vehicles if v.front >= threshold)
            q[road.head_junction] = q.get(road.head_junction, 0) + n
        return q


def _place(occ: np.ndarray, v: Vehicle, length: int, periodic: bool) -> None:
    for c in v.cells(length, periodic):
        occ[c] = 1


def _unplace(occ: np.ndarray, v: Vehicle, length: int, periodic: bool) -> None:
    for c in v.cells(length, periodic):
        occ[c] = 0
