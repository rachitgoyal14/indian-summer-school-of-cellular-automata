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

from src.core.gaps import front_gap

def decelerate_for_gap(vehicles: List[Vehicle]) -> None:
    """
    2. Decelerate: compute gap to the vehicle ahead.
    Uses front_gap from gaps.py to handle lateral overlaps.
    If speed > gap, speed = gap.
    """
    for v in vehicles:
        gap = front_gap(v, vehicles)
        if gap == float('inf'):
            continue
            
        gap = max(0.0, gap)
        if v.speed_cells_per_step > gap:
            v.speed_cells_per_step = int(gap)

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
