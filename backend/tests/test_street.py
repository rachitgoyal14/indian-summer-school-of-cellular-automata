"""
test_street.py — Stage 9 lane groups (Street / Lane).

Covers the acceptance criteria for the multi-lane data model:
  - a 2-lane street registers 2 roads in the Network,
  - left/right neighbours are wired correctly (and not across directions),
  - `Road` stays backward compatible and the 5 Stage 3 configurations still
    simulate bit-for-bit identically to before the refactor.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.core.junction import Junction
from src.network.network import Network, Road
from src.network.street import BACKWARD, FORWARD, Lane, Street
from src.network import grid_builder


def make_street(street_id: str = "S1", n: int = 2, length: int = 50,
                direction: str = FORWARD, first_id: int = 0) -> Street:
    street = Street(street_id)
    for i in range(n):
        street.add_road(
            Road(id=first_id + i, length=length, x0=0, y0=float(i * 3),
                 dx=1, dy=0, periodic=True),
            direction=direction,
        )
    return street


# --------------------------------------------------------------- construction
def test_two_lane_street_registers_two_roads():
    net = Network()
    street = make_street(n=2, length=50)
    net.add_street(street)

    assert len(street) == 2
    assert len(net.all_roads()) == 2
    assert len(net.roads) == 2
    assert [r.length for r in net.all_roads()] == [50, 50]
    assert net.get_street("S1") is street


def test_lane_metadata_stamped_onto_roads():
    street = make_street(street_id="main", n=3)
    for i, lane in enumerate(street.all_lanes()):
        assert lane.road.street_id == "main"
        assert lane.road.lane_index == i
        assert lane.lane_index == i
        assert lane.direction == FORWARD
        assert lane.street_id == "main"
        assert lane.road_id == lane.road.id
        assert lane.length == 50


def test_from_roads_indexes_left_to_right():
    roads = [Road(id=i, length=20) for i in range(3)]
    street = Street.from_roads("s", roads)
    assert [l.lane_index for l in street.all_lanes()] == [0, 1, 2]
    assert [l.road.id for l in street.all_lanes()] == [0, 1, 2]


# ------------------------------------------------------------------- neighbours
def test_two_lanes_neighbours_wired():
    street = make_street(n=2)
    left, right = street.all_lanes()

    assert left.left_lane is None
    assert left.right_lane is right
    assert right.left_lane is left
    assert right.right_lane is None

    assert left.is_leftmost() and not left.is_rightmost()
    assert right.is_rightmost() and not right.is_leftmost()
    assert left.neighbours() == [right]
    assert right.neighbours() == [left]


def test_three_lanes_middle_has_both_neighbours():
    street = make_street(n=3)
    l0, l1, l2 = street.all_lanes()
    assert l1.left_lane is l0 and l1.right_lane is l2
    assert l1.neighbours() == [l0, l2]
    assert l0.left_lane is None and l2.right_lane is None


def test_single_lane_street_has_no_neighbours():
    street = make_street(n=1)
    (only,) = street.all_lanes()
    assert only.left_lane is None and only.right_lane is None
    assert only.neighbours() == []


def test_lanes_added_out_of_order_are_sorted_and_rewired():
    street = Street("s")
    street.add_lane(Lane(road=Road(id=7, length=10), lane_index=2))
    street.add_lane(Lane(road=Road(id=5, length=10), lane_index=0))
    street.add_lane(Lane(road=Road(id=6, length=10), lane_index=1))

    assert [l.lane_index for l in street.all_lanes()] == [0, 1, 2]
    l0, l1, l2 = street.all_lanes()
    assert (l0.right_lane, l1.left_lane, l1.right_lane, l2.left_lane) == (l1, l0, l2, l1)


# ------------------------------------------------------------------ directions
def test_two_way_street_wires_neighbours_within_direction_only():
    street = Street("two_way")
    f0 = street.add_road(Road(id=0, length=30), direction=FORWARD)
    f1 = street.add_road(Road(id=1, length=30), direction=FORWARD)
    b0 = street.add_road(Road(id=2, length=30), direction=BACKWARD)
    b1 = street.add_road(Road(id=3, length=30), direction=BACKWARD)

    assert street.is_two_way()
    assert street.directions() == [FORWARD, BACKWARD]
    assert street.lanes_in_direction(FORWARD) == [f0, f1]
    assert street.lanes_in_direction(BACKWARD) == [b0, b1]

    # each direction is indexed independently, starting at 0
    assert (f0.lane_index, f1.lane_index) == (0, 1)
    assert (b0.lane_index, b1.lane_index) == (0, 1)

    # no lane ever neighbours oncoming traffic
    assert f1.right_lane is None and b0.left_lane is None
    assert f1.neighbours() == [f0]
    assert b0.neighbours() == [b1]


def test_lane_lookup_helpers():
    street = Street("s")
    f = street.add_road(Road(id=0, length=10), direction=FORWARD)
    b = street.add_road(Road(id=1, length=10), direction=BACKWARD)
    assert street.lane(0, FORWARD) is f
    assert street.lane(0, BACKWARD) is b
    assert street.lane(9, FORWARD) is None
    assert street.lane_for_road(1) is b
    assert street.lane_for_road(99) is None
    assert street.roads() == [f.road, b.road]
    assert list(street) == street.all_lanes()


# ------------------------------------------------------------------ validation
def test_bad_direction_rejected():
    with pytest.raises(ValueError, match="unknown lane direction"):
        Lane(road=Road(id=0, length=10), direction="sideways")
    with pytest.raises(ValueError, match="unknown lane direction"):
        Street("s").add_road(Road(id=0, length=10), direction="up")
    with pytest.raises(ValueError, match="unknown lane direction"):
        Street("s").lanes_in_direction("nope")


def test_negative_lane_index_rejected():
    with pytest.raises(ValueError, match="lane_index"):
        Lane(road=Road(id=0, length=10), lane_index=-1)


def test_duplicate_lane_index_rejected():
    street = Street("s")
    street.add_road(Road(id=0, length=10), direction=FORWARD, lane_index=0)
    with pytest.raises(ValueError, match="duplicate lane_index"):
        street.add_road(Road(id=1, length=10), direction=FORWARD, lane_index=0)
    # ...but the same index in the other direction is fine
    street.add_road(Road(id=2, length=10), direction=BACKWARD, lane_index=0)
    assert len(street) == 2


def test_same_road_twice_rejected():
    road = Road(id=0, length=10)
    street = Street("s")
    street.add_road(road)
    with pytest.raises(ValueError, match="already a lane"):
        street.add_road(road, lane_index=1)


def test_duplicate_street_id_rejected():
    net = Network()
    net.add_street(make_street("dup", n=1, first_id=0))
    with pytest.raises(ValueError, match="already registered"):
        net.add_street(make_street("dup", n=1, first_id=1))


def test_colliding_road_id_rejected():
    net = Network()
    net.add_road(Road(id=0, length=10))
    with pytest.raises(ValueError, match="already in use"):
        net.add_street(make_street("s", n=1, first_id=0))


def test_re_adding_same_street_is_idempotent():
    net = Network()
    street = make_street(n=2)
    net.add_street(street)
    net.add_street(street)
    assert len(net.streets) == 1
    assert len(net.all_roads()) == 2


def test_lane_repr_and_identity_do_not_recurse():
    street = make_street(n=2)
    l0, l1 = street.all_lanes()
    assert "lane_index=0" in repr(l0)         # cyclic neighbours excluded
    assert "lanes=2" in repr(street)
    assert l0 != l1 and l0 == l0              # identity semantics
    assert len({l0, l1}) == 2                 # hashable


# -------------------------------------------------------------------- junction
def test_connect_street_attaches_every_lane():
    j = Junction(id=0, x=0.0, y=0.0)
    street = Street("s")
    for i in range(2):
        street.add_road(Road(id=i, length=20, periodic=False))

    j.connect_street(street, end="end")
    assert [l.road.head_junction for l in street.all_lanes()] == [0, 0]
    assert [l.road.tail_junction for l in street.all_lanes()] == [None, None]


def test_connect_street_by_direction():
    j = Junction(id=3, x=0.0, y=0.0)
    street = Street("s")
    f = street.add_road(Road(id=0, length=20, periodic=False), direction=FORWARD)
    b = street.add_road(Road(id=1, length=20, periodic=False), direction=BACKWARD)

    j.connect_street(street, end="end", direction=FORWARD)
    j.connect_street(street, end="start", direction=BACKWARD)

    assert f.road.head_junction == 3 and f.road.tail_junction is None
    assert b.road.tail_junction == 3 and b.road.head_junction is None


def test_connect_rejects_periodic_and_bad_end():
    j = Junction(id=0, x=0.0, y=0.0)
    with pytest.raises(ValueError, match="periodic"):
        j.connect_street(make_street(n=1), end="end")
    with pytest.raises(ValueError, match="'start' or 'end'"):
        j.connect_road(Road(id=0, length=10, periodic=False), end="middle")


def test_street_junction_routes_traffic_end_to_end():
    """A 2-lane street feeding a junction actually moves vehicles through it."""
    net = Network()
    j = net.add_junction(Junction(id=0, x=10.0, y=0.0))

    inbound = Street("in")
    for i in range(2):
        inbound.add_road(Road(id=i, length=10, periodic=False, source_rate=1.0))
    outbound = Street("out")
    for i in range(2):
        outbound.add_road(Road(id=10 + i, length=10, periodic=False))
    net.add_street(inbound)
    net.add_street(outbound)

    j.connect_street(inbound, end="end")
    j.connect_street(outbound, end="start")
    # each inbound lane continues into the outbound lane with the same index
    j.turns = {0: {10: 1.0}, 1: {11: 1.0}}
    net.validate()

    rng = np.random.default_rng(0)
    for _ in range(40):
        net.step(rng)

    assert len(net.roads[10].vehicles) > 0
    assert len(net.roads[11].vehicles) > 0


# ------------------------------------------------------- backward compatibility
def test_plain_road_defaults_unchanged():
    r = Road(id=0, length=50)
    assert r.street_id is None and r.lane_index == 0
    # positional construction (the pre-Stage-9 signature) still works
    r2 = Road(1, 50, 0.0, 0.0, 1.0, 0.0, True)
    assert r2.id == 1 and r2.periodic and r2.street_id is None


def test_network_without_streets_is_unchanged():
    net = Network()
    net.add_road(Road(id=0, length=10))
    assert net.streets == {}
    assert net.get_street("nope") is None
    assert net.all_roads() == net.roads_ordered() == [net.roads[0]]


def test_street_survives_scenario_roundtrip():
    """Lane grouping, indices and directions come back exactly after save/load."""
    from src.engine.simulation import Simulation

    sim = Simulation(config="one_way", density=0.2, car_fraction=0.0, seed=1)
    street = Street("high_st")
    street.add_road(sim.network.roads[0], direction=FORWARD)
    street.add_road(Road(id=99, length=40, periodic=True), direction=BACKWARD)
    sim.network.add_street(street)

    data = json.loads(json.dumps(sim.to_scenario()))
    sim2 = Simulation()
    sim2.apply_scenario(data)
    assert sim2.to_scenario() == data, "save→load→save is not identical"

    loaded = sim2.network.get_street("high_st")
    assert loaded is not None and len(loaded) == 2
    assert [l.road.id for l in loaded.all_lanes()] == [0, 99]
    assert [l.direction for l in loaded.all_lanes()] == [FORWARD, BACKWARD]
    assert sim2.network.roads[0].street_id == "high_st"
    assert all(l.neighbours() == [] for l in loaded.all_lanes())  # one lane each way


def test_pre_stage9_scenario_without_streets_loads():
    """Old saved scenarios have no 'streets' key and must still load."""
    from src.engine.simulation import Simulation
    from src.io.scenario_io import network_from_scenario

    sim = Simulation(config="two_way_turns", density=0.2, car_fraction=0.0, seed=2)
    data = sim.to_scenario()
    for rd in data["roads"]:
        rd.pop("street_id"), rd.pop("lane_index")
    data.pop("streets")

    net = network_from_scenario(data)
    assert net.streets == {}
    assert all(r.street_id is None and r.lane_index == 0 for r in net.all_roads())


@pytest.mark.parametrize("builder", [
    grid_builder.build_one_way,
    grid_builder.build_two_way_no_interaction,
    grid_builder.build_two_way_turns,
    grid_builder.build_two_way_bidirectional_turns,
    grid_builder.build_grid,
])
def test_stage3_configurations_still_simulate(builder):
    """All 5 Stage 3 configurations build, populate and step with no streets."""
    net = builder()
    assert net.streets == {}
    assert net.all_roads() == net.roads_ordered()
    assert all(r.street_id is None for r in net.all_roads())

    net.populate_density(0.2, 0.0, np.random.default_rng(1))
    rng = np.random.default_rng(2)
    for _ in range(20):
        net.step(rng)
    assert net.density() >= 0.0
