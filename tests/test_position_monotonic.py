import pytest
import numpy as np
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_signal

def test_position_monotonic():
    config = load_config("configs/intersection_default.yaml")
    
    # We want a moderately congested test over a couple of cycles
    rate_veh_per_hour = 1200
    duration_s = 300 # > 2 cycles of 130s
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(42)
    df = run_single_leg_with_signal(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    # Group by vehicle_id and sort by time to check monotonicity
    for v_id, grp in df.groupby('vehicle_id'):
        grp = grp.sort_values('time_s')
        
        positions = grp['position_cells'].values
        
        # Calculate differences between consecutive timesteps
        diffs = np.diff(positions)
        
        # Position should never decrease
        assert np.all(diffs >= 0), f"Vehicle {v_id} moved backwards! Position diffs: {diffs[diffs < 0]}"
