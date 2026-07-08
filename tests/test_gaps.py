import pytest
from src.core.vehicle import Vehicle
from src.core.gaps import front_gap, lateral_gap

def test_front_gap():
    # v1 is leader, v2 is follower
    # v1: pos=20, len=5, lateral=2, width=3 -> long=[16, 20], lat=[2, 4]
    # v2: pos=10, len=5, lateral=3, width=2 -> long=[6, 10], lat=[3, 4]
    # Overlap laterally (3,4 intersects 2,4).
    # v1 back is 16, v2 front is 10. Gap = 16 - 10 - 1 = 5
    v1 = Vehicle(id=1, mode="car", length_cells=5, width_cells=3, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=20, lateral_position_cells=2)
    v2 = Vehicle(id=2, mode="car", length_cells=5, width_cells=2, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=10, lateral_position_cells=3)
    
    assert front_gap(v2, [v1]) == 5
    
    # v3: lateral=5, width=2 -> lat=[5, 6]. No lateral overlap with v1 [2,4]
    v3 = Vehicle(id=3, mode="car", length_cells=5, width_cells=2, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=10, lateral_position_cells=5)
    assert front_gap(v3, [v1]) == float('inf')
    
    # Longitudinal overlap -> gap 0
    v4 = Vehicle(id=4, mode="car", length_cells=5, width_cells=2, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=18, lateral_position_cells=3)
    assert front_gap(v4, [v1]) == 0.0

def test_lateral_gap():
    # v_main: pos=10, len=5 -> long=[6, 10]. lat=5, width=2 -> lat=[5, 6]
    v_main = Vehicle(id=1, mode="car", length_cells=5, width_cells=2, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=10, lateral_position_cells=5)
    
    # v_left: long=[7, 9] (overlaps main). lat=2, width=2 -> lat=[2, 3]
    # gap left = v_main_left(5) - v_left_right(3) - 1 = 1
    v_left = Vehicle(id=2, mode="car", length_cells=3, width_cells=2, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=9, lateral_position_cells=2)
    
    # v_right: long=[5, 8] (overlaps main). lat=9, width=3 -> lat=[9, 11]
    # gap right = v_right_left(9) - v_main_right(6) - 1 = 2
    v_right = Vehicle(id=3, mode="car", length_cells=4, width_cells=3, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=8, lateral_position_cells=9)
    
    g_left, g_right = lateral_gap(v_main, [v_left, v_right])
    assert g_left == 1
    assert g_right == 2
    
    # v_far_ahead: long=[15, 20] (NO overlap with [6, 10]). lat=2, width=2
    # Should not affect lateral gap
    v_far = Vehicle(id=4, mode="car", length_cells=6, width_cells=2, max_speed_cells_per_step=10, max_accel_cells_per_step2=1, position_cells=20, lateral_position_cells=2)
    g_left, g_right = lateral_gap(v_main, [v_far])
    assert g_left == float('inf')
    assert g_right == float('inf')
