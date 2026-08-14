"""
lane_change.py — the synchronous lateral (lane-changing) pre-pass (Stage 9).

Where it sits in a tick
-----------------------
    lateral transfer   <- this module
    longitudinal Rule 184 step   (Network.step pass A)
    junction transfers           (Network.step pass B)
    sources / sinks              (Network.step pass C)

The Rule 184 stepper is untouched. This pass only ever *moves whole vehicles
sideways between adjacent lanes of the same street and direction*, before any
longitudinal movement is computed. A vehicle keeps its id, `front`, `length`
and `vtype`; only which lane's vehicle list it lives on changes. Occupancy
grids are derived from those lists, so they follow automatically.

Decision rule
-------------
A vehicle changes lane only if all three hold:

  incentive  it cannot advance this step under the engine's own rule — the
             cell ahead is occupied or disrupted, or it is at the end of a
             periodic lane whose wrap cell is taken, or it is queueing at a
             junction that cannot accept it right now. A vehicle that can
             move, or that is about to leave through a sink, has no incentive.
  safety     every cell its footprint would occupy in the target lane, at the
             same longitudinal index, is free (plus `rear_safety_gap` cells
             behind it, which defaults to 0 — the strict v1 rule).
  gain       the move must actually help: the cell ahead of the landing
             footprint must be free too, so the vehicle can advance in the
             target lane. Without this a vehicle hops into a lane that is
             equally jammed and hops straight back the next tick, which
             flickers on screen and stops a blocked queue draining
             monotonically. Set `require_gain = False` for the plain
             "landing cells empty" rule.
  chance     a draw from the seeded RNG comes in under `lane_change_prob`.

The rear gap, and why it is 0
-----------------------------
`rear_safety_gap = 0` is deliberate for v1: only the landing footprint itself
has to be empty, so a vehicle may drop into the cell *directly in front of* a
follower already in the target lane. No collision can result from this — the
longitudinal pass resolves every move against one occupancy snapshot, so next
tick the follower simply reads that cell as occupied and holds. The cost is
purely to the follower's progress, and the gain rule caps even that: the
merging vehicle only lands where it can advance, so it is normally gone again
on the next tick and the follower loses about one step.

It does render as an aggressive merge. `net.rear_safety_gap = 1` makes a
vehicle refuse to cut in front of a follower at all; higher values demand a
longer clear run behind. Nothing else has to change — the gap cells go through
the same snapshot, vacated-cell and fixed-point logic as the landing cells.

Synchronicity
-------------
Nothing mutates until every intention is collected and resolved. Every gate
above reads one immutable occupancy snapshot taken before the pass.

Conflict resolution is symmetric and deterministic: if two or more vehicles
would land on overlapping cells, *all* of them are rejected and stay put. A
vehicle may move into cells that another vehicle is vacating in this same
pass, so a whole column of lanes can shuffle in one tick — but only if that
other vehicle really does leave. Because rejecting one mover can un-vacate a
cell another mover was counting on, acceptance is iterated to a fixed point:
the accepted set only ever shrinks, so it terminates in at most one round per
mover, and what survives is guaranteed collision-free.

Determinism
-----------
Exactly two RNG draws are consumed per *candidate* (a blocked vehicle with at
least one adjacent same-direction lane), in road-id then front order: one for
the probability test, one for which side it prefers when both neighbours are
open. The draw count depends only on the snapshot, never on how many
fixed-point rounds the resolver needs, so a seeded run is reproducible.

Drawing the probability before the safety test rather than after is
equivalent — the draw is independent of the outcome of the safety test — and
it is what keeps the RNG stream stable.

With `lane_change_prob == 0.0` (the default) or no streets registered, the
pass returns immediately and consumes no randomness at all, so a multi-lane
street steps bit-for-bit identically to the same lanes as independent roads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from src.core.vehicle import Vehicle

if TYPE_CHECKING:  # `network` imports this module, so keep the back-edge type-only
    from src.network.network import Network, Road


@dataclass
class _Move:
    """One vehicle's intention to shift sideways into a neighbouring lane."""

    vehicle: Vehicle
    src_id: int
    dst_id: int
    src_cells: tuple[int, ...]
    dst_cells: tuple[int, ...]
    # cells behind the landing footprint that must also stay clear (may be empty)
    rear_cells: tuple[int, ...] = field(default=())
    # the cell the vehicle would advance into next tick; must be free for the
    # move to be worth making (empty when the gain rule is off, or at a lane end)
    gain_cells: tuple[int, ...] = field(default=())

    def __hash__(self) -> int:  # identity: each intention is its own node
        return id(self)

    def __eq__(self, other: object) -> bool:
        return self is other


# --------------------------------------------------------------------- entry
def lane_change_pass(net: "Network", rng: np.random.Generator) -> int:
    """
    Run the lateral phase. Returns the number of vehicles that changed lane.

    Mutates only the roads' vehicle lists, and only after every intention has
    been collected and resolved against the pre-pass snapshot.
    """
    if net.lane_change_prob <= 0.0 or not net.streets:
        return 0

    lanes = _lane_neighbours(net)
    if not lanes:
        return 0

    occ = {rid: road.occupancy() for rid, road in net.roads.items()}
    moves = _collect(net, lanes, occ, rng)
    if not moves:
        return 0
    accepted = _resolve(net, occ, moves)
    return _apply(net, accepted)


# ---------------------------------------------------------------- collection
def _lane_neighbours(net: "Network") -> dict[int, list[int]]:
    """
    road_id → the road ids of its adjacent lanes, left first.

    Adjacency comes straight from the `Street` wiring, which only ever links
    lanes running the same direction — so oncoming lanes can never be targets.
    Lanes whose road is no longer in the network (removed by a map edit) are
    dropped.
    """
    out: dict[int, list[int]] = {}
    for street in net.streets_ordered():
        for lane in street.all_lanes():
            if lane.road.id not in net.roads:
                continue
            neighbours = [
                n.road.id for n in (lane.left_lane, lane.right_lane)
                if n is not None and n.road.id in net.roads
            ]
            if neighbours:
                out[lane.road.id] = neighbours
    return out


def _collect(
    net: "Network",
    lanes: dict[int, list[int]],
    occ: dict[int, np.ndarray],
    rng: np.random.Generator,
) -> list[_Move]:
    """Draw for every candidate and build the intention list, in a fixed order."""
    prob = net.lane_change_prob
    gap = max(0, int(net.rear_safety_gap))
    want_gain = bool(net.lane_change_require_gain)
    moves: list[_Move] = []

    for rid in sorted(lanes):
        road = net.roads[rid]
        for v in sorted(road.vehicles, key=lambda v: v.front):
            if not _is_blocked(net, road, rid, v, occ):
                continue
            # two draws per candidate, always, in this order — see module docs
            u = rng.random()
            side = rng.random()
            if u >= prob:
                continue
            order = lanes[rid] if side < 0.5 else list(reversed(lanes[rid]))
            src_cells = tuple(v.cells(road.length, road.periodic))
            for dst_id in order:
                landing = _landing(net.roads[dst_id], v, gap, want_gain)
                if landing is None:
                    continue
                dst_cells, rear_cells, gain_cells = landing
                if not _clear(net, occ, dst_id,
                              dst_cells + rear_cells + gain_cells):
                    continue
                moves.append(_Move(
                    vehicle=v, src_id=rid, dst_id=dst_id,
                    src_cells=src_cells, dst_cells=dst_cells,
                    rear_cells=rear_cells, gain_cells=gain_cells,
                ))
                break
    return moves


def _landing(
    dst: "Road", v: Vehicle, gap: int, want_gain: bool
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]] | None:
    """
    (footprint cells, the `gap` cells behind them, the cell ahead) for `v`
    landing on `dst` at the same longitudinal index. `None` if the lane cannot
    hold it there.

    `gap` is the optional rear safety margin — the cells a follower would have
    to be in to get cut off. It is 0 by default, giving the strict v1 rule of
    "the landing footprint must be empty", and the caller can raise it without
    any other change.

    The cell ahead is `front + 1`: the one the vehicle would advance into next
    tick, i.e. what makes the move worth it. At the open end of a lane there is
    no such cell — the vehicle exits or queues there — so the gain test is
    vacuous and the tuple is empty.
    """
    if v.front < 0 or v.front >= dst.length:
        return None
    body = [v.front - k for k in range(v.length)]
    tail = body[-1]
    ahead = v.front + 1
    if dst.periodic:
        body = [c % dst.length for c in body]
        gap = min(gap, dst.length - v.length)
        rear = [(tail - 1 - k) % dst.length for k in range(gap)]
        ahead %= dst.length
    else:
        if tail < 0:
            return None
        rear = [c for c in range(tail - 1, max(tail - 1 - gap, -1), -1)]
        if ahead >= dst.length:
            ahead = -1
    gain = (ahead,) if want_gain and ahead >= 0 else ()
    return tuple(body), tuple(rear), gain


def _is_blocked(
    net: "Network",
    road: "Road",
    rid: int,
    v: Vehicle,
    occ: dict[int, np.ndarray],
) -> bool:
    """
    True iff `v` cannot advance this step — the incentive to change lane.

    This mirrors `Network.step`'s own movement rule, so the incentive is
    exactly "the vehicle is stuck", footprint and all. The junction case is
    evaluated against the snapshot rather than the projected grid pass B will
    build, so it is an estimate of queueing: a vehicle is treated as stuck
    only when *no* outgoing lane could take it right now.
    """
    L = road.length
    nxt = v.front + 1
    if nxt < L:
        return not _free(net, occ, rid, nxt)
    if road.periodic:
        return not _free(net, occ, rid, nxt % L)
    if road.head_junction is None:
        return False  # sink: it leaves the network, never blocked
    j = net.junctions.get(road.head_junction)
    if j is None or rid not in j.turns:
        return True  # dead end: it can never leave
    entry = range(v.length)
    for out_id in j.turns[rid]:
        out = net.roads.get(out_id)
        if out is None or v.length > out.length:
            continue
        if all(_free(net, occ, out_id, c) for c in entry):
            return False
    return True


# ---------------------------------------------------------------- resolution
def _free(net: "Network", occ: dict[int, np.ndarray], rid: int, cell: int) -> bool:
    return occ[rid][cell] == 0 and cell not in net.blocked.get(rid, ())


def _clear(
    net: "Network",
    occ: dict[int, np.ndarray],
    rid: int,
    cells: tuple[int, ...],
    vacated: frozenset[int] = frozenset(),
) -> bool:
    """Every cell is empty in the snapshot (or freed by an accepted mover)."""
    blocked = net.blocked.get(rid, ())
    for c in cells:
        if c in blocked:
            return False          # a disrupted cell is never available
        if occ[rid][c] and c not in vacated:
            return False
    return True


def _resolve(
    net: "Network",
    occ: dict[int, np.ndarray],
    moves: list[_Move],
) -> list[_Move]:
    """
    Shrink the intention list to a collision-free set.

    Each round drops movers whose landing is no longer clear (because a
    vehicle they were counting on to vacate got dropped), then drops every
    mover in any group whose landing cells overlap. The set only shrinks, so
    the loop terminates; the survivors are pairwise disjoint and land only on
    cells that are empty or genuinely vacated.
    """
    accepted = list(moves)
    while True:
        vacated: dict[int, set[int]] = {}
        for m in accepted:
            vacated.setdefault(m.src_id, set()).update(m.src_cells)

        survivors = [
            m for m in accepted
            if _clear(net, occ, m.dst_id,
                      m.dst_cells + m.rear_cells + m.gain_cells,
                      frozenset(vacated.get(m.dst_id, ())))
        ]

        # symmetric conflict rule: overlapping landings cancel each other out
        claims: dict[tuple[int, int], list[_Move]] = {}
        for m in survivors:
            for c in m.dst_cells:
                claims.setdefault((m.dst_id, c), []).append(m)
        losers = {m for ms in claims.values() if len(ms) > 1 for m in ms}
        if losers:
            survivors = [m for m in survivors if m not in losers]

        # a move stops being worth making if another accepted mover is landing
        # on the very cell this one was counting on advancing into
        taken = {(m.dst_id, c) for m in survivors for c in m.dst_cells}
        survivors = [
            m for m in survivors
            if not any((m.dst_id, c) in taken for c in m.gain_cells)
        ]

        if len(survivors) == len(accepted):
            return survivors
        accepted = survivors


# ------------------------------------------------------------------- commit
def _apply(net: "Network", accepted: list[_Move]) -> int:
    """Move every accepted vehicle to its target lane, atomically per vehicle."""
    if not accepted:
        return 0
    leaving: dict[int, set[int]] = {}
    for m in accepted:
        leaving.setdefault(m.src_id, set()).add(id(m.vehicle))
    for rid, ids in leaving.items():
        road = net.roads[rid]
        # identity-based removal: the vehicle object itself is re-homed
        road.vehicles = [v for v in road.vehicles if id(v) not in ids]
    for m in accepted:
        net.roads[m.dst_id].vehicles.append(m.vehicle)
    for m in accepted:
        net.roads[m.dst_id].vehicles.sort(key=lambda v: v.front)
    return len(accepted)
