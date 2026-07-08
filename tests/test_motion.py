import numpy as np
from src.core.vehicle import Vehicle
from src.core.motion import accelerate, decelerate_for_gap, randomize, update_positions

def test_accelerate():
    v1 = Vehicle(id=1, mode="car", length_cells=7, width_cells=3, max_speed_cells_per_step=28, max_accel_cells_per_step2=3, speed_cells_per_step=0)
    accelerate([v1])
    assert v1.speed_cells_per_step == 3
    
    v1.speed_cells_per_step = 27
    accelerate([v1])
    assert v1.speed_cells_per_step == 28

def test_decelerate_for_gap():
    # v1 is ahead of v2
    # v1 front at 20, length 7 -> back at 20 - 7 + 1 = 14
    # v2 front at 5
    # gap = 14 - 5 - 1 = 8
    v1 = Vehicle(id=1, mode="car", length_cells=7, width_cells=3, max_speed_cells_per_step=28, max_accel_cells_per_step2=3, position_cells=20, speed_cells_per_step=5)
    v2 = Vehicle(id=2, mode="car", length_cells=7, width_cells=3, max_speed_cells_per_step=28, max_accel_cells_per_step2=3, position_cells=5, speed_cells_per_step=10)
    
    # Passing out of order to ensure sort works
    decelerate_for_gap([v2, v1])
    
    assert v1.speed_cells_per_step == 5
    assert v2.speed_cells_per_step == 8

def test_randomize():
    rng = np.random.default_rng(42)
    v1 = Vehicle(id=1, mode="car", length_cells=7, width_cells=3, max_speed_cells_per_step=28, max_accel_cells_per_step2=3, speed_cells_per_step=10)
    
    # 0 probability -> no slowdown
    randomize([v1], 0.0, rng)
    assert v1.speed_cells_per_step == 10
    
    # 1.0 probability -> slowdown
    randomize([v1], 1.0, rng)
    assert v1.speed_cells_per_step == 9
    
    # Cannot go below 0
    v1.speed_cells_per_step = 0
    randomize([v1], 1.0, rng)
    assert v1.speed_cells_per_step == 0

def test_update_positions():
    v1 = Vehicle(id=1, mode="car", length_cells=7, width_cells=3, max_speed_cells_per_step=28, max_accel_cells_per_step2=3, position_cells=10, speed_cells_per_step=5)
    v2 = Vehicle(id=2, mode="car", length_cells=7, width_cells=3, max_speed_cells_per_step=28, max_accel_cells_per_step2=3, position_cells=95, speed_cells_per_step=6) # Will cross 100
    
    survivors = update_positions([v1, v2], road_length_cells=100)
    assert len(survivors) == 1
    assert survivors[0].id == 1
    assert survivors[0].position_cells == 15
