from typing import List, Tuple
from src.core.vehicle import Vehicle

def front_gap(vehicle: Vehicle, other_vehicles: List[Vehicle]) -> float:
    """
    Longitudinal gap to nearest vehicle ahead whose lateral position overlaps this vehicle's lateral extent.
    Returns float('inf') if no vehicle ahead in the same lateral path.
    """
    min_gap = float('inf')
    v_left = vehicle.lateral_position_cells
    v_right = vehicle.lateral_position_cells + vehicle.width_cells - 1
    v_front = vehicle.position_cells
    v_back = vehicle.position_cells - vehicle.length_cells + 1
    
    for other in other_vehicles:
        if other.id == vehicle.id:
            continue
            
        o_left = other.lateral_position_cells
        o_right = other.lateral_position_cells + other.width_cells - 1
        
        # Check lateral overlap
        if v_left <= o_right and o_left <= v_right:
            o_back = other.position_cells - other.length_cells + 1
            o_front = other.position_cells
            
            if o_back > v_front:
                gap = o_back - v_front - 1
                if gap < min_gap:
                    min_gap = gap
            elif v_back <= o_front and o_back <= v_front:
                # Longitudinal overlap while laterally overlapping -> collision!
                return 0.0
                
    return min_gap

def lateral_gap(vehicle: Vehicle, other_vehicles: List[Vehicle]) -> Tuple[float, float]:
    """
    Minimum lateral clearance on left and right sides to vehicles overlapping the relevant longitudinal range.
    Returns (gap_left, gap_right).
    If no vehicles on a side, returns float('inf') for that side.
    """
    gap_left = float('inf')
    gap_right = float('inf')
    
    v_back = vehicle.position_cells - vehicle.length_cells + 1
    v_front_future = vehicle.position_cells + vehicle.speed_cells_per_step
    v_left = vehicle.lateral_position_cells
    v_right = vehicle.lateral_position_cells + vehicle.width_cells - 1
    
    for other in other_vehicles:
        if other.id == vehicle.id:
            continue
            
        o_back = other.position_cells - other.length_cells + 1
        o_front_future = other.position_cells + other.speed_cells_per_step
        
        # Check longitudinal overlap over the entire swept path to avoid collisions
        # We consider the union of current and future footprint for safety
        v_min_long = min(v_back, vehicle.position_cells - vehicle.length_cells + 1) # same
        v_max_long = v_front_future
        
        o_min_long = o_back
        o_max_long = o_front_future
        
        if v_min_long <= o_max_long and o_min_long <= v_max_long:
            o_left = other.lateral_position_cells
            o_right = other.lateral_position_cells + other.width_cells - 1
            
            if o_right < v_left:
                g = v_left - o_right - 1
                if g < gap_left:
                    gap_left = float(g)
            elif o_left > v_right:
                g = o_left - v_right - 1
                if g < gap_right:
                    gap_right = float(g)
            else:
                # Laterally and longitudinally overlapping
                return 0.0, 0.0
                
    return gap_left, gap_right
