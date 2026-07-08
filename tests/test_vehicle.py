from src.core.vehicle import Vehicle

def test_vehicle_creation():
    v = Vehicle(
        id=1,
        mode="car",
        length_cells=7,
        width_cells=3,
        max_speed_cells_per_step=28,
        max_accel_cells_per_step2=3
    )
    assert v.id == 1
    assert v.mode == "car"
    assert v.length_cells == 7
    assert v.width_cells == 3
    assert v.max_speed_cells_per_step == 28
    assert v.max_accel_cells_per_step2 == 3
    assert v.position_cells == 0
    assert v.lateral_position_cells == 0
    assert v.speed_cells_per_step == 0

    # Test mutability
    v.position_cells = 10
    v.speed_cells_per_step = 5
    assert v.position_cells == 10
    assert v.speed_cells_per_step == 5
