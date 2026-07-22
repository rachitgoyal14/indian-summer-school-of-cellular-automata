import pytest
import numpy as np
import pandas as pd
from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode

def test_no_overlap():
    config = load_config("configs/intersection_default.yaml")
    config['midblock_test']['road_length_m'] = 200 # shorter for test
    
    # Run a busy simulation
    rng = np.random.default_rng(42)
    mode_mix = {"two_wheeler": 0.4, "three_wheeler": 0.2, "car": 0.3, "bus": 0.1}
    
    df = run_midblock_simulation_multimode(config, rate_veh_per_hour=3000, duration_s=100, mode_mix=mode_mix, rng=rng)
    
    # We must construct a dictionary of modes to their lengths/widths from the config
    mode_params = config['mode_params']
    
    # Check for overlaps at each time step
    for t, group in df.groupby('time_s'):
        cells_occupied = set()
        
        for _, row in group.iterrows():
            mode = row['mode']
            length = mode_params[mode]['length_cells']
            width = mode_params[mode]['width_cells']
            
            p_long = row['position_cells']
            p_lat = row['lateral_position_cells']
            
            # Vehicle footprint
            for x in range(p_long - length + 1, p_long + 1):
                for y in range(p_lat, p_lat + width):
                    cell = (x, y)
                    assert cell not in cells_occupied, f"Collision detected at time {t} cell {cell}!"
                    cells_occupied.add(cell)
