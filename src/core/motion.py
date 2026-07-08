import numpy as np
from typing import List
from src.core.vehicle import Vehicle

def accelerate(vehicles: List[Vehicle]) -> None:
    """
    1. Accelerate: each vehicle's speed += max_accel_cells_per_step2, capped at its max_speed.
    (NaSch typically adds 1, but we use the vehicle's max accel)
    """
    for v in vehicles:
        v.speed_cells_per_step = min(
            v.max_speed_cells_per_step,
            v.speed_cells_per_step + v.max_accel_cells_per_step2
        )

def decelerate_for_gap(vehicles: List[Vehicle]) -> None:
    """
    2. Decelerate: compute gap to the vehicle ahead.
    Vehicles are assumed to be sorted by position (front-to-back, highest position first) or we must find the leader.
    In NaSch, gap = leader_rear_bumper - follower_front_bumper - 1.
    If speed > gap, speed = gap.
    """
    # Sort vehicles by position, descending (first vehicle is closest to end of road)
    vehicles_sorted = sorted(vehicles, key=lambda v: v.position_cells, reverse=True)
    
    for i in range(1, len(vehicles_sorted)):
        leader = vehicles_sorted[i-1]
        follower = vehicles_sorted[i]
        
        # gap = leader's back - follower's front - 1
        leader_back = leader.position_cells - leader.length_cells + 1
        gap = leader_back - follower.position_cells - 1
        
        # If leader is somehow overlapping or gap is negative, gap is 0
        gap = max(0, gap)
        
        if follower.speed_cells_per_step > gap:
            follower.speed_cells_per_step = gap

def randomize(vehicles: List[Vehicle], p_slowdown: float, rng: np.random.Generator) -> None:
    """
    3. Randomize: with probability p_slowdown, speed -= 1 (floor at 0).
    """
    for v in vehicles:
        if v.speed_cells_per_step > 0 and rng.random() < p_slowdown:
            v.speed_cells_per_step -= 1

def update_positions(vehicles: List[Vehicle], road_length_cells: int) -> List[Vehicle]:
    """
    4. Update positions: position += speed.
    Vehicles exceeding road_length_cells (position >= road_length_cells) are removed.
    Returns the updated list of vehicles that are still on the road.
    """
    surviving_vehicles = []
    for v in vehicles:
        v.position_cells += v.speed_cells_per_step
        if v.position_cells < road_length_cells:
            surviving_vehicles.append(v)
    return surviving_vehicles
