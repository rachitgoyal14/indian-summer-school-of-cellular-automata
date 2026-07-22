import pytest
import numpy as np
from src.core.vehicle import Vehicle
from src.core.lane_change import decide_lateral_move

def test_decide_lateral_move():
    # Helper to create a vehicle
    def make_v(lat):
        return Vehicle(
            id=1, mode="car", length_cells=7, width_cells=3,
            max_speed_cells_per_step=28, max_accel_cells_per_step2=3,
            position_cells=10, lateral_position_cells=lat
        )
        
    rng = np.random.default_rng(42)
    road_width = 10
    
    # 1. Normal free-lateral-move case
    v = make_v(5) # current_lat = 5
    # pref = 0.1 -> preferred_lat = round(0.1 * (10 - 3)) = round(0.7) = 1
    # Wants to move left (-1)
    # Gaps: left=1.0 (free), right=1.0 (free)
    # Since rng is deterministic, we just ensure lane_change_prob=1.0 to guarantee move
    move = decide_lateral_move(v, (1.0, 1.0), 0.1, 1.0, road_width, rng)
    assert move == -1
    
    v2 = make_v(2)
    # pref = 0.9 -> round(0.9 * 7) = 6
    # Wants to move right (+1)
    move = decide_lateral_move(v2, (1.0, 1.0), 0.9, 1.0, road_width, rng)
    assert move == 1
    
    # 2. Blocked case returns 0
    v_blocked = make_v(5) # Wants to move left (pref=0.1)
    # gap_left = 0.0 (blocked)
    move = decide_lateral_move(v_blocked, (0.0, 1.0), 0.1, 1.0, road_width, rng)
    assert move == 0
    
    v_blocked2 = make_v(2) # Wants to move right (pref=0.9)
    # gap_right = 0.0 (blocked)
    move = decide_lateral_move(v_blocked2, (1.0, 0.0), 0.9, 1.0, road_width, rng)
    assert move == 0
    
    # 3. lane_change_prob=0 always returns 0
    v_no_prob = make_v(5) # Wants to move left
    move = decide_lateral_move(v_no_prob, (1.0, 1.0), 0.1, 0.0, road_width, rng)
    assert move == 0
    
    # 4. Reached preferred position
    v_happy = make_v(1) # pref=0.1 -> 1
    move = decide_lateral_move(v_happy, (1.0, 1.0), 0.1, 1.0, road_width, rng)
    assert move == 0
    
    # 5. Boundary constraints
    v_left_edge = make_v(0)
    # Wants to move left (say preferred is somehow < 0, though not possible with 0.0-1.0)
    # Or just wants to stay, but let's test if it's at 0 it won't move left even if pref is 0.0
    move = decide_lateral_move(v_left_edge, (1.0, 1.0), 0.0, 1.0, road_width, rng)
    assert move == 0 # already at 0
    
    # What if preferred is 0, current is 0. Does not move.
