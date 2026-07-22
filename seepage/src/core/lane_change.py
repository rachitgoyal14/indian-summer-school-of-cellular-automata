import numpy as np
from typing import Tuple
from src.core.vehicle import Vehicle

def decide_lateral_move(
    vehicle: Vehicle,
    gaps: Tuple[float, float],
    position_preference: float,
    lane_change_prob: float,
    road_width_cells: int,
    rng: np.random.Generator
) -> int:
    """
    Decide whether to shift -1 (left), +1 (right), or 0 (stay).
    """
    # 1. Random draw
    if rng.random() >= lane_change_prob:
        return 0
        
    gap_left, gap_right = gaps
    
    # Calculate preferred lateral cell
    # 0 is the leftmost cell, road_width_cells - 1 is the rightmost.
    # We use (road_width_cells - vehicle.width_cells) to ensure the vehicle fits.
    max_lat = max(0, road_width_cells - vehicle.width_cells)
    preferred_lat = int(round(position_preference * max_lat))
    
    current_lat = vehicle.lateral_position_cells
    
    if current_lat == preferred_lat:
        return 0
        
    if preferred_lat < current_lat:
        # Wants to move left (-1)
        # Check if left is free and within road bounds
        if current_lat > 0 and gap_left >= 1: # needs at least 1 cell clearance
            return -1
    elif preferred_lat > current_lat:
        # Wants to move right (+1)
        if current_lat < max_lat and gap_right >= 1:
            return 1
            
    return 0
