import pandas as pd
from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import flow_density_by_mode
import numpy as np

config = load_config('configs/intersection_default.yaml')
config['midblock_test']['road_length_m'] = 1000

rates = [500, 1000, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 25000, 30000]
mode_mix = {
    'two_wheeler': 0.546,
    'three_wheeler': 0.256,
    'car': 0.036,
    'bus': 0.162
}
rng = np.random.default_rng(42)

for r in rates:
    df = run_midblock_simulation_multimode(config, r, 1000, mode_mix, rng)
    fd_dict = flow_density_by_mode(df, 2000, 0.5, 200, 50)
    fd_stable = fd_dict['all'].iloc[1:]
    avg_d = fd_stable['density_veh_per_km'].mean()
    avg_f = fd_stable['flow_veh_per_hr'].mean()
    print(f'Rate {r}: D={avg_d:.2f}, F={avg_f:.2f}')
