import pytest
from src.core.vehicle import Vehicle
from src.intersection.izoi import is_in_izoi, izoi_behavior

def create_car(pos, speed):
    return Vehicle(
        id=1, mode='car', length_cells=7, width_cells=3,
        max_speed_cells_per_step=28, max_accel_cells_per_step2=3,
        position_cells=pos, lateral_position_cells=0,
        speed_cells_per_step=speed
    )

def test_is_in_izoi():
    v = create_car(pos=900, speed=10) # Front of car is at 900+7 = 907
    stop_line = 1000
    izoi_dist = 100 # IZOI is 900 to 1000
    
    # Distance to stop line is 1000 - 900 - 7 = 93
    assert is_in_izoi(v, stop_line, izoi_dist) is True
    
    # Too far back
    v2 = create_car(pos=800, speed=10)
    assert is_in_izoi(v2, stop_line, izoi_dist) is False
    
    # Past stop line
    v3 = create_car(pos=1000, speed=10)
    assert is_in_izoi(v3, stop_line, izoi_dist) is False

def test_izoi_behavior_green():
    v = create_car(pos=900, speed=10)
    res = izoi_behavior(v, "green", field_decel_rate=2, min_gap=93)
    assert res == "midblock"
    assert v.speed_cells_per_step == 10 # unchanged

def test_izoi_behavior_red_deceleration():
    v = create_car(pos=900, speed=10)
    # Target gap is 93 to stop line. Speed is 10. Decel rate is 2.
    res = izoi_behavior(v, "red", field_decel_rate=2, min_gap=93)
    assert res == "decelerate_izoi"
    assert v.speed_cells_per_step == 8 # 10 - 2 = 8

    # Apply again
    izoi_behavior(v, "red", field_decel_rate=2, min_gap=85)
    assert v.speed_cells_per_step == 6

def test_izoi_behavior_red_gap_limit():
    # Close to stop line, large speed
    v = create_car(pos=990, speed=10)
    # Gap is 1000 - 990 - 7 = 3
    # Desired speed is 10 - 2 = 8, but gap is 3
    res = izoi_behavior(v, "red", field_decel_rate=2, min_gap=3)
    assert res == "decelerate_izoi"
    assert v.speed_cells_per_step == 3 # limited by gap
