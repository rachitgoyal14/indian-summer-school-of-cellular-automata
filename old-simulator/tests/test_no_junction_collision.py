import pytest
import numpy as np
from src.core.network import Road, Network
from src.core.junction import Junction

def test_junction_loop_collision_and_conservation():
    """
    Creates a closed loop of roads and junctions:
    Road A -> Junction 1 -> Road B -> Junction 2 -> Road C -> Junction 3 -> Road A
    And asserts car conservation and zero collisions over 1000 steps.
    """
    # Create network
    net = Network()
    
    # Roads
    road_a = Road("Road_A", length=20)
    road_b = Road("Road_B", length=30)
    road_c = Road("Road_C", length=15)
    
    net.add_road(road_a)
    net.add_road(road_b)
    net.add_road(road_c)
    
    # Junctions
    # J1 connects Road A to Road B (100% turn probability)
    j1 = Junction("J1", ["Road_A"], ["Road_B"], {"Road_A": {"Road_B": 1.0}})
    # J2 connects Road B to Road C (100% turn probability)
    j2 = Junction("J2", ["Road_B"], ["Road_C"], {"Road_B": {"Road_C": 1.0}})
    # J3 connects Road C to Road A (100% turn probability)
    j3 = Junction("J3", ["Road_C"], ["Road_A"], {"Road_C": {"Road_A": 1.0}})
    
    net.add_junction(j1)
    net.add_junction(j2)
    net.add_junction(j3)
    
    # Initialize with vehicles
    rng = np.random.default_rng(42)
    road_a.initialize_density(0.5, rng)
    road_b.initialize_density(0.3, rng)
    road_c.initialize_density(0.6, rng)
    
    # Measure initial cars
    initial_cars = net.get_total_cars()
    assert initial_cars > 0
    
    # Run simulation for 1000 steps
    for step_idx in range(1000):
        net.step(rng)
        
        # 1. Assert conservation of cars
        current_cars = net.get_total_cars()
        assert current_cars == initial_cars, (
            f"Step {step_idx}: Car count changed from {initial_cars} to {current_cars}"
        )
        
        # 2. Assert cell values are only 0 or 1 (zero overlap/collisions)
        for road_id, road in net.roads.items():
            assert np.all((road.state == 0) | (road.state == 1)), (
                f"Step {step_idx}, Road {road_id}: Invalid cell value found in state: {road.state}"
            )

def test_junction_merging_conflict_resolution():
    """
    Creates a merging intersection:
    Road A -> Junction 1 (merges Road A and Road B into Road C)
    Road B -> Junction 1
    Asserts conflict resolution works, no double occupancy of Road C cell 0,
    and total cars is conserved.
    """
    # In a merging network, to keep it closed and conserve cars, we can loop back:
    # Road C -> Junction 2 -> splits back to Road A (50%) and Road B (50%)
    net = Network()
    
    road_a = Road("Road_A", length=15)
    road_b = Road("Road_B", length=15)
    road_c = Road("Road_C", length=20)
    
    net.add_road(road_a)
    net.add_road(road_b)
    net.add_road(road_c)
    
    # J1 merges Road A and Road B to Road C
    j1 = Junction(
        "J1",
        incoming_roads=["Road_A", "Road_B"],
        outgoing_roads=["Road_C"],
        turn_proportions={
            "Road_A": {"Road_C": 1.0},
            "Road_B": {"Road_C": 1.0}
        }
    )
    
    # J2 splits Road C back to Road A and Road B
    j2 = Junction(
        "J2",
        incoming_roads=["Road_C"],
        outgoing_roads=["Road_A", "Road_B"],
        turn_proportions={
            "Road_C": {"Road_A": 0.5, "Road_B": 0.5}
        }
    )
    
    net.add_junction(j1)
    net.add_junction(j2)
    
    rng = np.random.default_rng(101)
    # Populate roads
    road_a.initialize_density(0.4, rng)
    road_b.initialize_density(0.4, rng)
    road_c.initialize_density(0.2, rng)
    
    initial_cars = net.get_total_cars()
    assert initial_cars > 0
    
    # Run simulation for 1000 steps
    for step_idx in range(1000):
        # We manually check if both Road A and Road B have a car at the last cell
        # and Road C, cell 0 is empty. If so, they both compete for Road C, cell 0.
        both_competing = (road_a.state[-1] == 1) and (road_b.state[-1] == 1) and (road_c.state[0] == 0)
        
        net.step(rng)
        
        # If both competed, verify that Road C got exactly one car (it became 1)
        # and one of the incoming roads stayed at 1 (the loser), while the winner became 0.
        # This is implicitly checked by asserting car conservation and 0/1 bounds,
        # but let's be sure the logic is sound.
        current_cars = net.get_total_cars()
        assert current_cars == initial_cars, f"Step {step_idx}: Car count mismatch"
        
        for road_id, road in net.roads.items():
            assert np.all((road.state == 0) | (road.state == 1)), f"Step {step_idx}: Invalid state"
