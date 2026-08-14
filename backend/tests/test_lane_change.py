"""
test_lane_change.py — Stage 9 synchronous lateral (lane-changing) pre-pass.

The guarantees under test:
  - `lane_change_prob = 0.0` leaves the physics bit-for-bit untouched,
  - blocked vehicles evacuate a jammed lane into a free neighbour,
  - no lane change ever produces an overlap or a footprint ghost,
  - a seeded run is reproducible,
  - the parameter survives resets, scenario round-trips and the WS channel.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from src.core.junction import Junction
from src.core.vehicle import Vehicle
from src.engine.simulation import Simulation
from src.network.network import Network, Road
from src.network.street import BACKWARD, FORWARD, Street


# --------------------------------------------------------------------- helpers
def two_lane_network(length: int = 60, lane_change_prob: float = 0.0,
                     periodic: bool = True) -> Network:
    net = Network()
    street = Street("S")
    for i in range(2):
        street.add_road(Road(id=i, length=length, x0=0, y0=float(i * 3),
                             dx=1, dy=0, periodic=periodic))
    net.add_street(street)
    net.lane_change_prob = lane_change_prob
    return net


def two_road_network(length: int = 60, periodic: bool = True) -> Network:
    """The same two lanes, but as plain independent roads (no street)."""
    net = Network()
    for i in range(2):
        net.add_road(Road(id=i, length=length, x0=0, y0=float(i * 3),
                          dx=1, dy=0, periodic=periodic))
    return net


def occupancy_fingerprint(net: Network, steps: int, seed: int) -> str:
    rng = np.random.default_rng(seed)
    h = hashlib.sha256()
    for _ in range(steps):
        h.update(str(net.step(rng)).encode())
        for r in net.roads_ordered():
            h.update(r.occupancy().tobytes())
    return h.hexdigest()


def assert_no_overlap(net: Network) -> None:
    """No cell may hold more than one vehicle, and footprints must be intact."""
    for road in net.roads_ordered():
        counts = np.zeros(road.length, dtype=int)
        for v in road.vehicles:
            cells = v.cells(road.length, road.periodic)
            assert len(cells) == v.length, (
                f"road {road.id}: vehicle {v.id} lost part of its footprint "
                f"({len(cells)} of {v.length} cells)"
            )
            assert len(set(cells)) == v.length, f"vehicle {v.id} self-overlaps"
            for c in cells:
                counts[c] += 1
        assert counts.max(initial=0) <= 1, (
            f"road {road.id}: occupancy > 1 at cells "
            f"{np.flatnonzero(counts > 1).tolist()}"
        )


def vehicle_census(net: Network) -> dict[int, tuple[int, str]]:
    return {v.id: (v.length, v.vtype) for r in net.roads.values() for v in r.vehicles}


# ---------------------------------------------------- zero-probability regression
@pytest.mark.parametrize("density", [0.1, 0.3, 0.6, 0.9])
@pytest.mark.parametrize("seed", [0, 7, 99])
def test_zero_prob_identical_to_independent_roads(density, seed):
    """`lane_change_prob = 0` ⇒ a street is bit-for-bit two independent roads."""
    street_net = two_lane_network(lane_change_prob=0.0)
    plain_net = two_road_network()
    for net in (street_net, plain_net):
        net.populate_density(density, 0.3, np.random.default_rng(seed))

    assert occupancy_fingerprint(street_net, 200, seed) == \
           occupancy_fingerprint(plain_net, 200, seed)


def test_zero_prob_consumes_no_randomness():
    """The lateral pass must not touch the RNG when it is switched off."""
    net = two_lane_network(lane_change_prob=0.0)
    net.populate_density(0.5, 0.0, np.random.default_rng(1))

    rng = np.random.default_rng(3)
    for _ in range(50):
        net.step(rng)
    after_street = rng.random()

    plain = two_road_network()
    plain.populate_density(0.5, 0.0, np.random.default_rng(1))
    rng2 = np.random.default_rng(3)
    for _ in range(50):
        plain.step(rng2)

    assert after_street == rng2.random()
    assert net.last_lane_changes == 0


def test_no_streets_means_no_lateral_pass():
    net = two_road_network()
    net.lane_change_prob = 1.0          # on, but nothing is grouped into a street
    net.populate_density(0.5, 0.0, np.random.default_rng(1))
    rng = np.random.default_rng(2)
    net.step(rng)
    assert net.last_lane_changes == 0


# ------------------------------------------------------------------- evacuation
def test_blocked_lane_evacuates_into_free_neighbour():
    """
    Lane 0 is permanently obstructed at cell 20; lane 1 is empty. The vehicles
    queued behind the obstruction must migrate across and pass it, and lane 0's
    queue must only ever shrink.
    """
    net = two_lane_network(length=60, lane_change_prob=1.0, periodic=False)
    lane0, lane1 = net.roads[0], net.roads[1]
    net.blocked[0] = {20}                     # an immovable obstruction
    for c in range(10, 20):                   # ten vehicles queued behind it
        lane0.vehicles.append(Vehicle(net.new_vid(), c, 1, "moto"))
    queued_ids = {v.id for v in lane0.vehicles}
    assert len(queued_ids) == 10

    rng = np.random.default_rng(0)
    queue_lengths = []
    seen_past = set()
    for _ in range(80):
        net.step(rng)
        assert_no_overlap(net)
        # the queue is what is still stuck *behind* the obstruction in lane 0;
        # a vehicle may legitimately drop back into lane 0 past cell 20
        queue_lengths.append(sum(1 for v in lane0.vehicles if v.front < 20))
        seen_past |= {v.id for v in net.all_vehicles() if v.front > 20}

    # every queued vehicle left lane 0 ...
    assert queue_lengths[-1] == 0
    # ... monotonically, never re-entering the jam
    assert all(b <= a for a, b in zip(queue_lengths, queue_lengths[1:]))
    # ... and every one of them got past the obstruction
    assert seen_past == queued_ids
    # nothing ever crossed the obstruction itself: cell 20 stayed empty in lane 0
    assert lane0.occupancy()[20] == 0


def test_moving_vehicle_does_not_change_lane():
    """No incentive without a blockage: free-flowing traffic stays put."""
    net = two_lane_network(length=40, lane_change_prob=1.0, periodic=True)
    net.roads[0].vehicles.append(Vehicle(1, 5, 1, "moto"))
    rng = np.random.default_rng(0)
    for _ in range(20):
        net.step(rng)
    assert len(net.roads[0].vehicles) == 1 and not net.roads[1].vehicles


def test_sink_bound_vehicle_is_not_blocked():
    """A vehicle at an open lane end leaves the network; it must not swerve."""
    net = two_lane_network(length=20, lane_change_prob=1.0, periodic=False)
    net.roads[0].vehicles.append(Vehicle(1, 19, 1, "moto"))
    rng = np.random.default_rng(0)
    net.step(rng)
    assert not net.roads[0].vehicles and not net.roads[1].vehicles


def test_queueing_at_a_junction_is_an_incentive():
    """A vehicle stuck at a junction whose exit is full may change lane."""
    net = Network()
    j = net.add_junction(Junction(id=0, x=0.0, y=0.0))
    street = Street("in")
    for i in range(2):
        street.add_road(Road(id=i, length=10, periodic=False, head_junction=0))
    net.add_street(street)
    out = net.add_road(Road(id=5, length=4, periodic=False, tail_junction=0))
    j.turns = {0: {5: 1.0}, 1: {5: 1.0}}
    net.validate()
    net.lane_change_prob = 1.0

    # the outgoing lane is completely full, so nothing can leave the junction
    for c in range(4):
        out.vehicles.append(Vehicle(net.new_vid(), c, 1, "moto"))
    stuck = Vehicle(net.new_vid(), 9, 1, "moto")
    net.roads[0].vehicles.append(stuck)

    net.step(np.random.default_rng(0))
    assert net.last_lane_changes == 1
    assert [v.id for v in net.roads[1].vehicles] == [stuck.id]


# ------------------------------------------------------------------- collisions
@pytest.mark.parametrize("density", [0.3, 0.6])
def test_no_collisions_over_1000_steps(density):
    net = two_lane_network(length=80, lane_change_prob=0.5, periodic=True)
    net.populate_density(density, 0.4, np.random.default_rng(5))
    before = vehicle_census(net)

    rng = np.random.default_rng(11)
    for _ in range(1000):
        net.step(rng)
        assert_no_overlap(net)

    # a periodic network conserves vehicles, footprints and types exactly
    assert vehicle_census(net) == before


def test_head_on_conflict_rejects_both():
    """Two vehicles wanting the same cell from opposite sides both stay put."""
    net = Network()
    street = Street("S")
    for i in range(3):
        street.add_road(Road(id=i, length=10, periodic=False))
    net.add_street(street)
    net.lane_change_prob = 1.0

    # lanes 0 and 2 each hold a vehicle blocked at cell 5; lane 1 is their only
    # free neighbour, and both would land on cell 5 of it.
    for rid in (0, 2):
        net.roads[rid].vehicles.append(Vehicle(net.new_vid(), 5, 1, "moto"))
        net.roads[rid].vehicles.append(Vehicle(net.new_vid(), 6, 1, "moto"))

    from src.network.lane_change import lane_change_pass
    changed = lane_change_pass(net, np.random.default_rng(0))

    assert changed == 0
    assert not net.roads[1].vehicles
    assert len(net.roads[0].vehicles) == len(net.roads[2].vehicles) == 2


# -------------------------------------------------------------------- the gain
def test_gain_rule_refuses_an_equally_jammed_lane():
    """No point swerving into a lane that is blocked at the same place."""
    net = two_lane_network(length=20, lane_change_prob=1.0, periodic=False)
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 5, 1, "moto"))
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 6, 1, "moto"))  # blocks it
    net.roads[1].vehicles.append(Vehicle(net.new_vid(), 6, 1, "moto"))  # same wall

    from src.network.lane_change import lane_change_pass
    assert lane_change_pass(net, np.random.default_rng(0)) == 0

    # clear lane 1's wall and the same vehicle crosses immediately
    net.roads[1].vehicles.clear()
    assert lane_change_pass(net, np.random.default_rng(0)) == 1


def test_require_gain_off_restores_the_literal_rule():
    net = two_lane_network(length=20, lane_change_prob=1.0, periodic=False)
    net.lane_change_require_gain = False
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 5, 1, "moto"))
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 6, 1, "moto"))
    net.roads[1].vehicles.append(Vehicle(net.new_vid(), 6, 1, "moto"))

    from src.network.lane_change import lane_change_pass
    assert lane_change_pass(net, np.random.default_rng(0)) == 1


def test_rear_safety_gap_blocks_a_cut_off():
    """With a rear gap the vehicle refuses to cut in front of a follower."""
    net = two_lane_network(length=20, lane_change_prob=1.0, periodic=False)
    net.rear_safety_gap = 2
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 10, 1, "moto"))
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 11, 1, "moto"))  # blocks it
    follower = Vehicle(net.new_vid(), 9, 1, "moto")                      # in the gap
    net.roads[1].vehicles.append(follower)

    from src.network.lane_change import lane_change_pass
    assert lane_change_pass(net, np.random.default_rng(0)) == 0

    net.roads[1].vehicles.remove(follower)
    assert lane_change_pass(net, np.random.default_rng(0)) == 1


# ----------------------------------------------------------- cars vs motorbikes
def test_car_needs_both_target_cells_free():
    """A 2-cell car may not land where only one of its two cells is free."""
    net = two_lane_network(length=20, lane_change_prob=1.0, periodic=False)
    car = Vehicle(net.new_vid(), 10, 2, "car")          # would occupy 9, 10
    net.roads[0].vehicles.append(car)
    net.roads[0].vehicles.append(Vehicle(net.new_vid(), 11, 1, "moto"))  # blocks it
    net.roads[1].vehicles.append(Vehicle(net.new_vid(), 9, 1, "moto"))   # blocks cell 9

    from src.network.lane_change import lane_change_pass
    assert lane_change_pass(net, np.random.default_rng(0)) == 0
    assert car in net.roads[0].vehicles

    # free cell 9 in the target lane and the car crosses, footprint intact
    net.roads[1].vehicles.clear()
    assert lane_change_pass(net, np.random.default_rng(0)) == 1
    assert car not in net.roads[0].vehicles
    moved = net.roads[1].vehicles[0]
    assert (moved.id, moved.front, moved.length, moved.vtype) == \
           (car.id, 10, 2, "car")
    assert sorted(moved.cells(20, False)) == [9, 10]
    assert_no_overlap(net)
    assert int(net.roads[0].occupancy().sum()) == 1   # no ghost cells left behind


def test_car_footprint_preserved_under_heavy_lane_changing():
    net = two_lane_network(length=50, lane_change_prob=1.0, periodic=True)
    net.populate_density(0.5, 1.0, np.random.default_rng(4))
    assert any(v.vtype == "car" for v in net.all_vehicles())
    before = vehicle_census(net)

    rng = np.random.default_rng(9)
    for _ in range(300):
        net.step(rng)
        assert_no_overlap(net)
    assert vehicle_census(net) == before


# ------------------------------------------------------------ direction safety
def test_opposing_lanes_are_never_targets():
    """A forward lane and a backward lane of one street are not neighbours."""
    net = Network()
    street = Street("two_way")
    street.add_road(Road(id=0, length=12, periodic=False), direction=FORWARD)
    street.add_road(Road(id=1, length=12, periodic=False), direction=BACKWARD)
    net.add_street(street)
    net.lane_change_prob = 1.0

    net.roads[0].vehicles.append(Vehicle(1, 5, 1, "moto"))
    net.roads[0].vehicles.append(Vehicle(2, 6, 1, "moto"))  # blocks vehicle 1

    from src.network.lane_change import lane_change_pass
    assert lane_change_pass(net, np.random.default_rng(0)) == 0
    assert not net.roads[1].vehicles


# ------------------------------------------------------------------ determinism
def test_same_seed_same_final_state():
    def run(seed: int) -> str:
        net = two_lane_network(length=70, lane_change_prob=0.3, periodic=True)
        net.populate_density(0.4, 0.3, np.random.default_rng(2))
        return occupancy_fingerprint(net, 500, seed)

    assert run(21) == run(21)
    assert run(21) != run(22)


def test_lane_changes_reported_per_step():
    net = two_lane_network(length=60, lane_change_prob=1.0, periodic=True)
    net.populate_density(0.5, 0.0, np.random.default_rng(3))
    rng = np.random.default_rng(4)
    total = 0
    for _ in range(50):
        net.step(rng)
        assert net.last_lane_changes >= 0
        total += net.last_lane_changes
    assert total > 0


# ------------------------------------------------------- parameter plumbing
def test_prob_is_clamped_and_reaches_the_network():
    sim = Simulation(config="one_way", density=0.2, seed=1, lane_change_prob=0.4)
    assert sim.network.lane_change_prob == 0.4
    sim.set_lane_change_prob(5.0)
    assert sim.lane_change_prob == 1.0 and sim.network.lane_change_prob == 1.0
    sim.set_lane_change_prob(-1.0)
    assert sim.lane_change_prob == 0.0 and sim.network.lane_change_prob == 0.0


def test_prob_persists_across_reset_and_config_switch():
    sim = Simulation(config="one_way", density=0.2, seed=1, lane_change_prob=0.25)
    sim.reset()
    assert sim.network.lane_change_prob == 0.25
    sim.load_config("grid")
    assert sim.network.lane_change_prob == 0.25
    sim.reset(lane_change_prob=0.75)
    assert sim.lane_change_prob == 0.75 and sim.network.lane_change_prob == 0.75


def test_all_three_params_reach_the_network():
    sim = Simulation(config="one_way", density=0.2, seed=1,
                     lane_change_prob=0.4, rear_safety_gap=2,
                     lane_change_require_gain=False)
    assert (sim.network.lane_change_prob,
            sim.network.rear_safety_gap,
            sim.network.lane_change_require_gain) == (0.4, 2, False)

    sim.set_lane_change_params(rear_gap=3)          # partial update
    assert sim.network.rear_safety_gap == 3
    assert sim.network.lane_change_prob == 0.4      # untouched
    assert sim.network.lane_change_require_gain is False

    sim.set_lane_change_params(require_gain=True, prob=0.1)
    assert (sim.lane_change_prob, sim.rear_safety_gap,
            sim.lane_change_require_gain) == (0.1, 3, True)
    sim.set_lane_change_params(rear_gap=-5)
    assert sim.rear_safety_gap == 0                 # clamped


def test_all_three_params_persist_across_reset_and_config_switch():
    sim = Simulation(config="one_way", density=0.2, seed=1,
                     lane_change_prob=0.25, rear_safety_gap=2,
                     lane_change_require_gain=False)
    for act in (lambda: sim.reset(), lambda: sim.load_config("grid")):
        act()
        assert (sim.network.lane_change_prob,
                sim.network.rear_safety_gap,
                sim.network.lane_change_require_gain) == (0.25, 2, False)

    sim.reset(rear_safety_gap=4, lane_change_require_gain=True)
    assert sim.network.rear_safety_gap == 4
    assert sim.network.lane_change_require_gain is True


def test_all_three_params_survive_scenario_roundtrip():
    sim = Simulation(config="one_way", density=0.2, seed=1,
                     lane_change_prob=0.6, rear_safety_gap=2,
                     lane_change_require_gain=False)
    data = json.loads(json.dumps(sim.to_scenario()))
    sim2 = Simulation()
    sim2.apply_scenario(data)

    assert (sim2.lane_change_prob, sim2.rear_safety_gap,
            sim2.lane_change_require_gain) == (0.6, 2, False)
    assert (sim2.network.lane_change_prob,
            sim2.network.rear_safety_gap,
            sim2.network.lane_change_require_gain) == (0.6, 2, False)
    assert sim2.to_scenario() == data
    # and they survive the reset that a loaded scenario implies
    sim2.reset()
    assert sim2.network.rear_safety_gap == 2
    assert sim2.network.lane_change_require_gain is False


def test_loaded_scenario_reproduces_step_for_step():
    """
    The Prompt 3 guarantee: save → load → step must track the original exactly,
    with every lateral knob off its default.
    """
    sim = Simulation(config="two_way_no_interaction", density=0.35,
                     car_fraction=0.3, seed=5, lane_change_prob=0.5,
                     rear_safety_gap=1, lane_change_require_gain=False)
    street = Street("S")
    for rid in sorted(sim.network.roads):
        street.add_road(sim.network.roads[rid], direction=FORWARD)
    sim.network.add_street(street)
    sim._scenario_structure = sim._structure_snapshot()

    for _ in range(25):
        sim.advance()
    data = json.loads(json.dumps(sim.to_scenario()))

    clone = Simulation()
    clone.apply_scenario(data)
    for _ in range(75):
        sim.advance()
        clone.advance()
    assert clone.to_scenario() == sim.to_scenario()


def test_pre_stage9_scenario_omitting_lane_params_loads():
    sim = Simulation(config="one_way", density=0.2, seed=1)
    data = sim.to_scenario()
    for key in ("lane_change_prob", "rear_safety_gap", "lane_change_require_gain"):
        data.pop(key)

    from src.io.scenario_io import network_from_scenario
    net = network_from_scenario(data)
    assert net.lane_change_prob == 0.0
    assert net.rear_safety_gap == 0
    assert net.lane_change_require_gain is True


def test_prob_survives_scenario_roundtrip():
    sim = Simulation(config="one_way", density=0.2, seed=1, lane_change_prob=0.6)
    data = json.loads(json.dumps(sim.to_scenario()))
    sim2 = Simulation()
    sim2.apply_scenario(data)
    assert sim2.lane_change_prob == 0.6
    assert sim2.network.lane_change_prob == 0.6
    assert sim2.to_scenario() == data


def test_websocket_control_channel():
    from fastapi.testclient import TestClient
    from src.server.ws_server import app, manager

    manager.sim = Simulation(config="one_way", density=0.2, seed=1)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()  # network
        ws.receive_json()  # state
        ws.send_json({"type": "pause"})
        ws.send_json({"type": "set_lane_change_prob", "p": 0.35})
        state = None
        for _ in range(12):
            msg = ws.receive_json()
            if msg.get("type") == "state" and msg.get("lane_change_prob") == 0.35:
                state = msg
                break
        assert state is not None, "lane_change_prob was not broadcast"
        assert "lane_changes" in state["analytics"]

        # partial update: rear_gap only, prob must be left alone
        ws.send_json({"type": "set_lane_change_params", "rear_gap": 2,
                      "require_gain": False})
        state = None
        for _ in range(12):
            msg = ws.receive_json()
            if msg.get("type") == "state" and msg.get("rear_safety_gap") == 2:
                state = msg
                break
        assert state is not None, "rear_safety_gap was not broadcast"
        assert state["lane_change_prob"] == 0.35
        assert state["lane_change_require_gain"] is False

    assert manager.sim.network.lane_change_prob == 0.35
    assert manager.sim.network.rear_safety_gap == 2
    assert manager.sim.network.lane_change_require_gain is False
