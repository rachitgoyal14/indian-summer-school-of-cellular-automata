import pandas as pd
from src.metrics.density_flow import flow_density_from_log

def test_flow_density_from_log():
    # 2 vehicles, 3 time steps
    # road_length_cells = 100, cell_length_m = 1.0 (road = 0.1 km)
    # window = 3s
    # density = avg vehicles (which is 2 * 3 / 3 = 2) / 0.1 = 20 veh/km
    
    records = [
        {"time_s": 0, "vehicle_id": 1, "position_cells": 88, "speed_cells_per_step": 2},
        {"time_s": 0, "vehicle_id": 2, "position_cells": 10, "speed_cells_per_step": 5},
        
        {"time_s": 1, "vehicle_id": 1, "position_cells": 90, "speed_cells_per_step": 2}, # crosses 90
        {"time_s": 1, "vehicle_id": 2, "position_cells": 15, "speed_cells_per_step": 5},
        
        {"time_s": 2, "vehicle_id": 1, "position_cells": 92, "speed_cells_per_step": 2},
        {"time_s": 2, "vehicle_id": 2, "position_cells": 20, "speed_cells_per_step": 5},
        
        # add a dummy time 3 so window 0-3 works
        {"time_s": 3, "vehicle_id": 1, "position_cells": 94, "speed_cells_per_step": 2},
    ]
    df = pd.DataFrame(records)
    
    # measurement point is road_length_cells - 10 = 90
    # vehicle 1 crosses 90 at t=1. (pos=90, prev=88, speed=2, 90-2 = 88 < 90)
    # flow = 1 vehicle * (3600 / 3) = 1200 veh/hr
    
    # Actually the window logic goes up to max_time, so max_time is 3, windows are [0, 3].
    result = flow_density_from_log(df, road_length_cells=100, cell_length_m=1.0, window_s=3, measurement_point_offset=10)
    
    assert len(result) == 1
    res_row = result.iloc[0]
    
    assert res_row["density_veh_per_km"] == 20.0
    assert res_row["flow_veh_per_hr"] == 1200.0
