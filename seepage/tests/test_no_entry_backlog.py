import pytest
import numpy as np
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_signal

def test_no_entry_backlog():
    config = load_config("configs/intersection_default.yaml")
    
    # Use a moderate demand level
    rate_veh_per_hour = 1000
    duration_s = 390 # 3 cycles
    
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(123)
    df = run_single_leg_with_signal(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    # Pending count is logged for every vehicle on the road.
    # We assert that the maximum pending_count at any logged timestep is very small (e.g., < 2).
    # Ideally it is 0.
    if 'pending_count' in df.columns:
        max_pending = df['pending_count'].max()
        assert max_pending <= 2, f"Entry backlog detected! Max pending vehicles was {max_pending}."
    else:
        pytest.fail("pending_count column not found in output DataFrame.")
