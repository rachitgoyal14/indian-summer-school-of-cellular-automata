"""
test_multilane_import.py — Stage 11 multi-lane OSM import and grid extension.

Covers lane-count parsing from OSM tags, the perpendicular geometric offsets,
junction wiring for multi-lane streets, and the procedural grid's
`lanes_per_direction` parameter — plus the backward-compatibility guarantees
that untagged ways and single-lane grids behave exactly as they did before.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pytest

from src.engine.simulation import Simulation
from src.io.scenario_io import network_from_scenario
from src.mapdata.cell_scale import METERS_PER_CELL
from src.mapdata.osm_to_network import osm_to_network, parse_lanes
from src.network import grid_builder
from src.network.lane_geometry import (
    LANE_WIDTH_CELLS,
    LANE_WIDTH_M,
    perpendicular_right,
    slot_offset,
    street_slot,
)
from src.network.network import Network
from src.network.street import BACKWARD, FORWARD, Street


# --------------------------------------------------------------------- fixture
#   N1 ---- N2 ---- N3        A: N1→N2  oneway, lanes=2   → 2 forward
#            |                B: N2→N3  two-way, lanes=4  → 2 fwd + 2 bwd
#            N4               C: N2→N4  two-way, untagged → 1 fwd + 1 bwd
NODES = {
    1: {"lat": 25.2600, "lon": 82.9900},
    2: {"lat": 25.2600, "lon": 82.9920},
    3: {"lat": 25.2600, "lon": 82.9935},
    4: {"lat": 25.2609, "lon": 82.9920},
}

WAYS = [
    {"id": 100, "nodes": [1, 2],
     "tags": {"highway": "primary", "name": "A", "oneway": "yes", "lanes": "2"}},
    {"id": 200, "nodes": [2, 3],
     "tags": {"highway": "primary", "name": "B", "lanes": "4"}},
    {"id": 300, "nodes": [2, 4],
     "tags": {"highway": "residential", "name": "C"}},
]


def osm(ways=None, nodes=None) -> Network:
    return osm_to_network({"nodes": nodes or NODES, "ways": ways or WAYS})


def street_named(net: Network, way_id: int) -> Street:
    for street in net.streets.values():
        if street.id.startswith(f"w{way_id}_"):
            return street
    raise AssertionError(f"no street from way {way_id}; have {sorted(net.streets)}")


def fingerprint(net: Network, steps: int, seed: int) -> str:
    rng = np.random.default_rng(seed)
    h = hashlib.sha256()
    for _ in range(steps):
        h.update(str(net.step(rng)).encode())
        for r in net.roads_ordered():
            h.update(r.occupancy().tobytes())
    return h.hexdigest()


# ------------------------------------------------------------------ tag parsing
@pytest.mark.parametrize("tags, expected", [
    ({"oneway": "yes", "lanes": "2"}, (2, 0)),
    ({"oneway": "yes", "lanes": "3"}, (3, 0)),
    ({"oneway": "no", "lanes": "2"}, (1, 1)),
    ({"oneway": "no", "lanes": "4"}, (2, 2)),
    ({"oneway": "no", "lanes": "3"}, (2, 1)),      # odd: extra lane forward
    ({"oneway": "no", "lanes": "1"}, (1, 1)),      # still needs a lane each way
    ({"oneway": "no"}, (1, 1)),                    # the pre-Stage-11 default
    ({"oneway": "yes"}, (1, 0)),
    ({}, (1, 1)),
    ({"oneway": "1", "lanes": "2"}, (2, 0)),
    ({"oneway": "true", "lanes": "2"}, (2, 0)),
    ({"lanes": "banana"}, (1, 1)),                 # malformed → default
    ({"lanes": "0"}, (1, 1)),
    ({"lanes": "-2"}, (1, 1)),
    ({"lanes": ""}, (1, 1)),
    ({"oneway": "yes", "lanes": "banana"}, (1, 0)),
    ({"oneway": "no", "lanes": " 4 "}, (2, 2)),    # whitespace tolerated
])
def test_parse_lanes(tags, expected):
    forward, backward, why = parse_lanes(tags)
    assert (forward, backward) == expected
    assert why, "every choice must carry a reason for the import log"


def test_parse_lanes_explains_itself():
    assert "no usable lanes tag" in parse_lanes({})[2]
    assert "malformed" in parse_lanes({"lanes": "two"})[2]
    assert "oneway" in parse_lanes({"oneway": "yes", "lanes": "2"})[2]


# ------------------------------------------------------------------- geometry
def test_perpendicular_is_the_drivers_right():
    # +y is downward on screen, so a driver heading east has south on the right
    assert perpendicular_right(1, 0) == (0.0, 1.0)
    assert perpendicular_right(0, 1) == (-1.0, 0.0)
    assert perpendicular_right(0, 0) == (0.0, 0.0)
    px, py = perpendicular_right(3, 4)
    assert math.isclose(math.hypot(px, py), 1.0)


def test_slot_offsets_are_centred_on_the_baseline():
    assert slot_offset(0, 1, 3.5) == 0.0                 # single lane: on it
    assert slot_offset(0, 2, 3.5) == -1.75               # two: straddling
    assert slot_offset(1, 2, 3.5) == 1.75
    assert [slot_offset(i, 3, 3.5) for i in range(3)] == [-3.5, 0.0, 3.5]


def test_street_slots_tile_the_width_without_overlap():
    # 2 forward + 2 backward: forward takes the left half (drive on the left)
    slots = [street_slot(i, FORWARD, 2, 2) for i in range(2)]
    slots += [street_slot(i, BACKWARD, 2, 2) for i in range(2)]
    assert sorted(slots) == [0, 1, 2, 3], slots
    assert slots[:2] == [0, 1]           # forward lanes on the left
    # the backward driver's own leftmost lane is the far edge of the road
    assert slots[2:] == [3, 2]


def test_lane_width_constants_agree():
    assert math.isclose(LANE_WIDTH_CELLS * METERS_PER_CELL, LANE_WIDTH_M)


# --------------------------------------------------------------- OSM structure
def test_oneway_with_two_lanes_makes_two_forward_lanes():
    street = street_named(osm(), 100)
    assert len(street) == 2
    assert street.directions() == [FORWARD]
    lanes = street.lanes_in_direction(FORWARD)
    assert [lane.lane_index for lane in lanes] == [0, 1]
    assert lanes[0].right_lane is lanes[1]
    assert lanes[1].left_lane is lanes[0]
    assert lanes[0].left_lane is None and lanes[1].right_lane is None


def test_two_way_with_four_lanes_splits_two_each_way():
    street = street_named(osm(), 200)
    assert len(street) == 4
    assert street.is_two_way()
    for direction in (FORWARD, BACKWARD):
        lanes = street.lanes_in_direction(direction)
        assert [lane.lane_index for lane in lanes] == [0, 1]
        assert lanes[0].right_lane is lanes[1] and lanes[1].left_lane is lanes[0]
        # never adjacent to oncoming traffic
        assert lanes[0].left_lane is None and lanes[1].right_lane is None
    fwd = street.lanes_in_direction(FORWARD)[0]
    bwd = street.lanes_in_direction(BACKWARD)[0]
    assert (fwd.road.dx, fwd.road.dy) == (-bwd.road.dx, -bwd.road.dy)


def test_untagged_way_is_one_lane_each_way():
    street = street_named(osm(), 300)
    assert len(street) == 2
    assert [lane.direction for lane in street.all_lanes()] == [FORWARD, BACKWARD]
    # a single lane each way has no lateral neighbour: no lane changing
    assert all(lane.neighbours() == [] for lane in street.all_lanes())


def test_untagged_import_matches_pre_stage11_road_count():
    """Ways with no lanes tag must import exactly as they used to."""
    plain = [{"id": w["id"], "nodes": w["nodes"],
              "tags": {k: v for k, v in w["tags"].items() if k != "lanes"}}
             for w in WAYS]
    net = osm(ways=plain)
    # way A oneway (1) + way B two-way (2) + way C two-way (2)
    assert len(net.roads) == 5
    assert all(len(s) <= 2 for s in net.streets.values())


def test_cells_scale_linearly_with_lane_count():
    one = [{"id": 100, "nodes": [1, 2], "tags": {"oneway": "yes"}},
           {"id": 200, "nodes": [2, 3], "tags": {"oneway": "yes"}}]
    two = [dict(w, tags=dict(w["tags"], lanes="2")) for w in one]

    cells_one = sum(r.length for r in osm(ways=one).roads.values())
    cells_two = sum(r.length for r in osm(ways=two).roads.values())
    assert cells_two == 2 * cells_one


def test_lane_geometry_is_offset_and_deterministic():
    net = osm()
    street = street_named(net, 100)
    a, b = (lane.road for lane in street.all_lanes())

    # parallel, same length, but not on top of each other
    assert (a.dx, a.dy) == (b.dx, b.dy)
    assert a.length == b.length
    separation = math.hypot(a.x0 - b.x0, a.y0 - b.y0)
    assert math.isclose(separation, LANE_WIDTH_M, rel_tol=1e-9), separation

    # importing the same data twice gives byte-identical coordinates
    again = street_named(osm(), 100)
    assert [(l.road.x0, l.road.y0, l.road.dx, l.road.dy)
            for l in street.all_lanes()] == \
           [(l.road.x0, l.road.y0, l.road.dx, l.road.dy)
            for l in again.all_lanes()]


def test_no_two_lanes_share_a_centreline():
    net = osm()
    for street in net.streets.values():
        origins = [(round(l.road.x0, 6), round(l.road.y0, 6))
                   for l in street.all_lanes()]
        assert len(set(origins)) == len(origins), f"{street.id} lanes overlap"


def test_lane_offset_does_not_change_cell_count():
    """Lane width is a rendering concern: it must not touch the physics."""
    for street in osm().streets.values():
        lengths = {lane.road.length for lane in street.all_lanes()}
        assert len(lengths) == 1, "lanes of one street must be the same length"


# ------------------------------------------------------- OSM junction wiring
def test_every_lane_connects_to_the_junction():
    net = osm()
    incoming = {r.id for r in net.roads.values() if r.head_junction is not None}
    for street in net.streets.values():
        attached = {l.road.id for l in street.all_lanes()
                    if l.road.head_junction is not None
                    or l.road.tail_junction is not None}
        assert attached, f"street {street.id} reaches no junction"
    assert incoming, "no lane feeds any junction"


def test_turns_are_index_matched_and_links_are_recorded():
    net = osm()
    for j in net.junctions.values():
        for in_rid, outs in j.turns.items():
            assert math.isclose(sum(outs.values()), 1.0, abs_tol=1e-9)
            in_lane = net.roads[in_rid].lane_index
            for out_rid in outs:
                out = net.roads[out_rid]
                group = [r for r in net.roads.values()
                         if r.street_id == out.street_id
                         and r.tail_junction == j.id]
                widest = max(r.lane_index for r in group)
                assert out.lane_index == min(in_lane, widest), (
                    f"lane {in_lane} entered lane {out.lane_index} of a "
                    f"{widest + 1}-lane street"
                )
            # the full lane-to-lane graph is kept for future restricted turns
            assert in_rid in j.lane_links
            assert set(outs).issubset(j.lane_links[in_rid])


def test_imported_multilane_network_simulates_without_collisions():
    net = osm()
    net.lane_change_prob = 0.5
    net.populate_density(0.3, 0.3, np.random.default_rng(1))
    rng = np.random.default_rng(2)
    for _ in range(300):
        net.step(rng)
        for road in net.roads_ordered():
            counts = np.zeros(road.length, dtype=int)
            for v in road.vehicles:
                for c in v.cells(road.length, road.periodic):
                    counts[c] += 1
            assert counts.max(initial=0) <= 1


# ------------------------------------------------------------- procedural grid
def test_single_lane_grid_is_unchanged():
    """lanes_per_direction=1 must be the pre-Stage-11 grid, to the coordinate."""
    net = grid_builder.build_grid(rows=2, cols=2, seg=40)
    assert net.streets == {}
    assert len(net.roads) == 12
    assert all(r.street_id is None and r.lane_index == 0
               for r in net.roads.values())
    # geometry sits exactly on the baseline — no offset applied
    assert (net.roads[0].x0, net.roads[0].y0) == (-40, 0)
    assert (net.roads[1].x0, net.roads[1].y0) == (0, 0)
    # junction (0,0): H_in=0 → H_out=1 straight / V_out=7 turn, and vice versa
    assert net.junctions[0].turns == {0: {1: 0.6, 7: 0.4}, 6: {7: 0.6, 1: 0.4}}
    assert net.junctions[0].lane_links == {0: [1, 7], 6: [7, 1]}


def test_two_lane_grid_structure():
    net = grid_builder.build_grid(rows=2, cols=2, seg=40, lanes_per_direction=2)
    assert len(net.roads) == 24            # twice the single-lane count
    assert len(net.streets) == 12
    assert sum(r.length for r in net.roads.values()) == 960

    for street in net.streets.values():
        lanes = street.all_lanes()
        assert [l.lane_index for l in lanes] == [0, 1]
        assert lanes[0].right_lane is lanes[1]
        assert lanes[1].left_lane is lanes[0]
        assert lanes[0].left_lane is None and lanes[1].right_lane is None
        a, b = (l.road for l in lanes)
        assert math.isclose(math.hypot(a.x0 - b.x0, a.y0 - b.y0),
                            LANE_WIDTH_CELLS, rel_tol=1e-9)


@pytest.mark.parametrize("lanes", [1, 2, 3])
def test_grid_cells_scale_linearly(lanes):
    net = grid_builder.build_grid(rows=2, cols=2, seg=40,
                                  lanes_per_direction=lanes)
    assert len(net.roads) == 12 * lanes
    assert sum(r.length for r in net.roads.values()) == 480 * lanes


def test_grid_junctions_wire_every_lane():
    net = grid_builder.build_grid(rows=2, cols=2, seg=40, lanes_per_direction=2)
    for j in net.junctions.values():
        # both lanes of both incoming streets are routed
        assert len(j.turns) == 4
        for in_rid, outs in j.turns.items():
            assert math.isclose(sum(outs.values()), 1.0, abs_tol=1e-9)
            in_lane = net.roads[in_rid].lane_index
            assert all(net.roads[o].lane_index == in_lane for o in outs)
            assert len(j.lane_links[in_rid]) == 4   # every outgoing lane
    net.validate()


def test_grid_multilane_simulates():
    net = grid_builder.build_grid(rows=3, cols=3, seg=30, lanes_per_direction=2)
    net.lane_change_prob = 0.4
    rng = np.random.default_rng(5)
    for _ in range(200):
        net.step(rng)
    assert sum(len(r.vehicles) for r in net.roads.values()) > 0


# ----------------------------------------- zero-probability regression (Prompt 2)
def test_two_lane_grid_with_zero_prob_matches_independent_roads():
    """
    The Prompt 2 guarantee, on a procedurally generated 2-lane grid: with
    lane_change_prob = 0 the streets are indistinguishable from the same
    lanes as plain independent roads.
    """
    streeted = grid_builder.build_grid(rows=2, cols=2, seg=40,
                                       lanes_per_direction=2)
    streeted.lane_change_prob = 0.0

    plain = grid_builder.build_grid(rows=2, cols=2, seg=40,
                                    lanes_per_direction=2)
    plain.streets = {}                      # same roads, no lane grouping
    for road in plain.roads.values():
        road.street_id = None

    for net in (streeted, plain):
        net.populate_density(0.3, 0.3, np.random.default_rng(9))

    assert fingerprint(streeted, 200, 13) == fingerprint(plain, 200, 13)


# ------------------------------------------------------------------ round-trip
def test_multilane_grid_round_trips_and_reruns_identically():
    sim = Simulation(config="grid", density=0.3, car_fraction=0.3, seed=6,
                     lane_change_prob=0.4,
                     build_kwargs={"rows": 2, "cols": 2, "seg": 40,
                                   "lanes_per_direction": 2})
    assert len(sim.network.streets) == 12
    for _ in range(20):
        sim.advance()

    data = json.loads(json.dumps(sim.to_scenario()))
    clone = Simulation()
    clone.apply_scenario(data)

    assert len(clone.network.streets) == 12
    assert clone.to_scenario() == data
    for a, b in zip(clone.network.roads_ordered(), sim.network.roads_ordered()):
        assert (a.x0, a.y0, a.dx, a.dy, a.street_id, a.lane_index) == \
               (b.x0, b.y0, b.dx, b.dy, b.street_id, b.lane_index)

    for _ in range(60):
        sim.advance()
        clone.advance()
    assert clone.to_scenario() == sim.to_scenario()


def test_imported_network_round_trips():
    sim = Simulation()
    sim.network = osm()
    data = json.loads(json.dumps(sim.to_scenario()))
    net = network_from_scenario(data)

    assert len(net.streets) == len(sim.network.streets)
    for sid, street in sim.network.streets.items():
        loaded = net.get_street(sid)
        assert loaded is not None
        assert [(l.lane_index, l.direction, l.road.id)
                for l in loaded.all_lanes()] == \
               [(l.lane_index, l.direction, l.road.id)
                for l in street.all_lanes()]


def test_lane_links_survive_the_round_trip():
    sim = Simulation(config="grid", seed=1,
                     build_kwargs={"rows": 2, "cols": 2, "lanes_per_direction": 2})
    data = json.loads(json.dumps(sim.to_scenario()))
    net = network_from_scenario(data)
    for jid, j in sim.network.junctions.items():
        assert net.junctions[jid].lane_links == {
            k: sorted(v) for k, v in j.lane_links.items()
        }


# ------------------------------------------------------------------ housekeeping
def test_removing_a_road_prunes_its_lane():
    sim = Simulation(config="grid", seed=1,
                     build_kwargs={"rows": 2, "cols": 2, "lanes_per_direction": 2})
    street = next(iter(sim.network.streets.values()))
    victim, survivor = (lane.road.id for lane in street.all_lanes())

    sim.remove_road(victim)

    assert len(street) == 1
    assert street.all_lanes()[0].road.id == survivor
    assert street.all_lanes()[0].neighbours() == []
    # the scenario still round-trips: no lane points at a road that is gone
    data = json.loads(json.dumps(sim.to_scenario()))
    network_from_scenario(data)


def test_removing_every_lane_drops_the_street():
    net = grid_builder.build_grid(rows=2, cols=2, lanes_per_direction=2)
    street = next(iter(net.streets.values()))
    for road in list(street.roads()):
        del net.roads[road.id]
    assert net.prune_streets() == 2
    assert street.id not in net.streets
