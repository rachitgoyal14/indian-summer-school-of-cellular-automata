from typing import Literal

def is_in_izoi(vehicle, stop_line_position_cells: int, izoi_distance_cells: int) -> bool:
    # A vehicle is in IZOI if it is before the stop line, but within izoi_distance_cells
    dist_to_stop = stop_line_position_cells - vehicle.position_cells - vehicle.length_cells
    if 0 <= dist_to_stop <= izoi_distance_cells:
        return True
    return False

def izoi_behavior(vehicle, signal_state: Literal["green", "red"], field_decel_rate: int, min_gap: int) -> str:
    """
    Implements Algorithm 2:
    - if in IZOI and signal is RED: decelerate at field_decel_rate with NO randomization.
    - if in IZOI and signal is GREEN: continue as midblock (return 'midblock').
    
    Returns the action taken ('decelerate_izoi' or 'midblock').
    If 'decelerate_izoi', the vehicle's speed is reduced and randomization should be skipped.
    """
    if signal_state == "red":
        # Decelerate smoothly to stop at the stop line or behind lead vehicle
        # We assume the gap includes distance to stop line if there is no leader.
        desired_speed = vehicle.speed_cells_per_step - field_decel_rate
        # Ensure we don't hit the vehicle ahead or cross the stop line
        v_next = int(max(0, min(desired_speed, min_gap)))  # int cast: field_decel_rate is float(2.0)
        vehicle.speed_cells_per_step = v_next
        return "decelerate_izoi"
    else:
        # Green signal -> continue as midblock
        return "midblock"
