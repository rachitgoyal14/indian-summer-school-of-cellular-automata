"""
grid_builder.py — the 5 brief-specified lane/junction configurations.

The brief lists these "case by case"; they are built here in order:

  1. one_way                      single periodic ring road (Stage 1/2 baseline)
  2. two_way_no_interaction       two independent parallel rings, opposite dirs
  3. two_way_turns                one inflow splitting at a junction (turn or go straight)
  4. two_way_bidirectional_turns  an intersection of two directions, each turning
  5. grid                         procedural R×C multi-junction connected network

Every builder returns a validated `Network`. Config (1) is the exact Stage 1
periodic ring, so the mathematical baseline is preserved and re-tested.
"""

from __future__ import annotations

from src.core.junction import Junction
from src.network.network import Network, Road


# --------------------------------------------------------------------------- 1
def build_one_way(length: int = 500) -> Network:
    """Case 1 — a single one-way periodic (ring) road. The Stage 1 baseline."""
    net = Network()
    net.add_road(Road(id=0, length=length, x0=0, y0=0, dx=1, dy=0, periodic=True))
    net.validate()
    return net


# --------------------------------------------------------------------------- 2
def build_two_way_no_interaction(length: int = 400) -> Network:
    """
    Case 2 — two parallel one-way rings travelling in opposite directions,
    sharing no cells (hence 'no interaction'). Rendered as two stacked lanes.
    """
    net = Network()
    # eastbound ring on top
    net.add_road(Road(id=0, length=length, x0=0, y0=0, dx=1, dy=0, periodic=True))
    # westbound ring below: geometry draws right-to-left (dx=-1) so travel
    # direction reads oppositely on screen; still an independent periodic lane.
    net.add_road(Road(id=1, length=length, x0=length, y0=3, dx=-1, dy=0, periodic=True))
    net.validate()
    return net


# --------------------------------------------------------------------------- 3
def build_two_way_turns(seg: int = 120, straight_bias: float = 0.6,
                        source_rate: float = 0.4, car_fraction: float = 0.3) -> Network:
    """
    Case 3 — an inflow road reaching a junction where each vehicle either
    continues straight or turns off onto a side road (weighted proportions).
    """
    net = Network()
    j = 0
    net.add_junction(Junction(id=j, x=seg, y=0))
    # incoming (source at tail, head feeds the junction)
    net.add_road(Road(id=0, length=seg, x0=0, y0=0, dx=1, dy=0, periodic=False,
                      head_junction=j, source_rate=source_rate,
                      source_car_fraction=car_fraction))
    # straight-through (east), sink at head
    net.add_road(Road(id=1, length=seg, x0=seg, y0=0, dx=1, dy=0, periodic=False,
                      tail_junction=j))
    # turn (south), sink at head
    net.add_road(Road(id=2, length=seg, x0=seg, y0=0, dx=0, dy=1, periodic=False,
                      tail_junction=j))
    net.junctions[j].turns = {0: {1: straight_bias, 2: round(1 - straight_bias, 6)}}
    net.validate()
    return net


# --------------------------------------------------------------------------- 4
def build_two_way_bidirectional_turns(seg: int = 120, straight_bias: float = 0.6,
                                      source_rate: float = 0.35,
                                      car_fraction: float = 0.3) -> Network:
    """
    Case 4 — an intersection fed from two directions (west and north), each
    incoming stream either continuing straight or turning, so both directions
    have turns. Two sources, two sinks, one junction.
    """
    net = Network()
    j = 0
    net.add_junction(Junction(id=j, x=seg, y=seg))
    # incoming from west (eastbound)
    net.add_road(Road(id=0, length=seg, x0=0, y0=seg, dx=1, dy=0, periodic=False,
                      head_junction=j, source_rate=source_rate,
                      source_car_fraction=car_fraction))
    # incoming from north (southbound)
    net.add_road(Road(id=1, length=seg, x0=seg, y0=0, dx=0, dy=1, periodic=False,
                      head_junction=j, source_rate=source_rate,
                      source_car_fraction=car_fraction))
    # outgoing east (sink)
    net.add_road(Road(id=2, length=seg, x0=seg, y0=seg, dx=1, dy=0, periodic=False,
                      tail_junction=j))
    # outgoing south (sink)
    net.add_road(Road(id=3, length=seg, x0=seg, y0=seg, dx=0, dy=1, periodic=False,
                      tail_junction=j))
    turn = round(1 - straight_bias, 6)
    net.junctions[j].turns = {
        0: {2: straight_bias, 3: turn},   # from west: straight=east, turn=south
        1: {3: straight_bias, 2: turn},   # from north: straight=south, turn=east
    }
    net.validate()
    return net


# --------------------------------------------------------------------------- 5
def build_grid(rows: int = 2, cols: int = 2, seg: int = 40,
               straight_bias: float = 0.6, source_rate: float = 0.4,
               car_fraction: float = 0.3) -> Network:
    """
    Case 5 — a procedural R×C grid of junctions.

    Horizontal roads flow east, vertical roads flow south. Boundary roads on
    the west/north edges are sources (inflow); on the east/south edges they
    are sinks (outflow). Every junction has exactly one incoming and one
    outgoing road in each of the two orientations, so routing is uniform:
    a vehicle either goes straight (same orientation) or turns (perpendicular).
    """
    net = Network()

    # junctions at grid positions (world = cell coords)
    jid = {}
    n = 0
    for r in range(rows):
        for c in range(cols):
            jid[(r, c)] = n
            net.add_junction(Junction(id=n, x=c * seg, y=r * seg))
            n += 1

    rid = 0
    h_seg: dict[tuple[int, int], int] = {}  # (row, s) -> road id, s in 0..cols
    v_seg: dict[tuple[int, int], int] = {}  # (col, t) -> road id, t in 0..rows

    # horizontal roads (flow east)
    for r in range(rows):
        for s in range(cols + 1):
            tail = jid[(r, s - 1)] if s >= 1 else None
            head = jid[(r, s)] if s <= cols - 1 else None
            net.add_road(Road(
                id=rid, length=seg, x0=(s - 1) * seg, y0=r * seg, dx=1, dy=0,
                periodic=False, head_junction=head, tail_junction=tail,
                source_rate=source_rate if tail is None else 0.0,
                source_car_fraction=car_fraction,
            ))
            h_seg[(r, s)] = rid
            rid += 1

    # vertical roads (flow south)
    for c in range(cols):
        for t in range(rows + 1):
            tail = jid[(t - 1, c)] if t >= 1 else None
            head = jid[(t, c)] if t <= rows - 1 else None
            net.add_road(Road(
                id=rid, length=seg, x0=c * seg, y0=(t - 1) * seg, dx=0, dy=1,
                periodic=False, head_junction=head, tail_junction=tail,
                source_rate=source_rate if tail is None else 0.0,
                source_car_fraction=car_fraction,
            ))
            v_seg[(c, t)] = rid
            rid += 1

    # wire turns: every junction has H_in, V_in, H_out, V_out
    turn = round(1 - straight_bias, 6)
    for r in range(rows):
        for c in range(cols):
            H_in = h_seg[(r, c)]
            V_in = v_seg[(c, r)]
            H_out = h_seg[(r, c + 1)]
            V_out = v_seg[(c, r + 1)]
            net.junctions[jid[(r, c)]].turns = {
                H_in: {H_out: straight_bias, V_out: turn},
                V_in: {V_out: straight_bias, H_out: turn},
            }

    net.validate()
    return net


# --------------------------------------------------------------------------- registry
BUILDERS = {
    "one_way": build_one_way,
    "two_way_no_interaction": build_two_way_no_interaction,
    "two_way_turns": build_two_way_turns,
    "two_way_bidirectional_turns": build_two_way_bidirectional_turns,
    "grid": build_grid,
}

# brief case number → config name
CASE_TO_CONFIG = {
    1: "one_way",
    2: "two_way_no_interaction",
    3: "two_way_turns",
    4: "two_way_bidirectional_turns",
    5: "grid",
}


def build(config: str, **kwargs) -> Network:
    if config not in BUILDERS:
        raise ValueError(f"unknown config {config!r}; choices: {list(BUILDERS)}")
    return BUILDERS[config](**kwargs)
