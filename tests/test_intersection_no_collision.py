import pytest
import numpy as np
from src.core.config import load_config
from src.sim.sim_loop import run_full_intersection
from src.intersection.intersection import Intersection

def test_intersection_no_collision():
    config = load_config("configs/intersection_default.yaml")
    
    # Run a busy intersection to force interaction
    rate_veh_per_hour = 1500
    duration_s = 260 # 2 full cycles of 130s
    
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(999)
    df = run_full_intersection(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    # We need to reconstruct the 2D junction box occupancy for each time step
    # and assert no two vehicles occupy the same cell at the same time.
    # Fortunately, we can re-use the Intersection class's logic to map 1D pos to 2D cells.
    
    inter = Intersection(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    stop_line_cells = inter.legs[0].stop_line_position_cells
    
    # For speed, we just loop over the dataframe time-by-time
    mode_params = config['mode_params']
    
    for t, grp in df.groupby("time_s"):
        occupancy = {}
        for _, row in grp.iterrows():
            pos_past = row["position_cells"] - stop_line_cells
            if pos_past >= 0 and pos_past < 2 * inter.box_size:
                leg_id = row["leg_origin"]
                lat_pos = row["lateral_position_cells"]
                turn = row["turn"]
                mode = row["mode"]
                v_id = row["vehicle_id"]
                
                v_length = mode_params[mode]['length_cells']
                v_width = mode_params[mode]['width_cells']
                
                cells = inter.get_junction_cells(leg_id, lat_pos, turn, pos_past, v_length, v_width)
                for c in cells:
                    if c in occupancy:
                        other_v_id = occupancy[c]
                        pytest.fail(f"Collision in junction box at t={t}, cell={c} between vehicle {v_id} and {other_v_id}")
                    occupancy[c] = v_id
