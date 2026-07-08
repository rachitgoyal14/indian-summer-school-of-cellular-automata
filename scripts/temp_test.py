import numpy as np
import pandas as pd
from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation
from src.metrics.density_flow import flow_density_from_log

def test_fd(p_slowdown, road_length, rates):
    config = load_config('configs/intersection_default.yaml')
    config['midblock_test']['road_length_m'] = road_length
    config['simulation']['p_slowdown'] = p_slowdown
    
    print(f"\n--- Testing p_slowdown={p_slowdown}, road={road_length}m ---")
    for rate in rates:
        rng = np.random.default_rng(42)
        df = run_midblock_simulation(config, rate, 3600, rng)
        fd = flow_density_from_log(df, int(road_length/0.5), 0.5, 300)
        if len(fd) > 1:
            avg_d = fd["density_veh_per_km"].iloc[1:].mean()
            avg_f = fd["flow_veh_per_hr"].iloc[1:].mean()
            print(f'Rate {rate:5d} : density={avg_d:5.2f} veh/km, flow={avg_f:7.2f} veh/hr')

if __name__ == "__main__":
    rates_sweep = [1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000]
    # Test 1: baseline (p=0.06, 1000m)
    test_fd(0.06, 1000, rates_sweep)
    # Test 2: higher p_slowdown (p=0.3, 1000m)
    test_fd(0.3, 1000, rates_sweep)
    # Test 3: higher p_slowdown and longer road (p=0.3, 3000m)
    test_fd(0.3, 3000, rates_sweep)
