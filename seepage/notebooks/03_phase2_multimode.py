import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import flow_density_by_mode

def main():
    config = load_config("../configs/intersection_default.yaml")
    config['midblock_test']['road_length_m'] = 1000
    
    # 8-10 traffic volumes
    rates = [500, 1000, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 25000, 30000]
    duration_s = 3600
    rng = np.random.default_rng(42)
    
    # Real Kanagaraj mode proportions (calculated from data/processed/trajectories_kanagaraj.csv)
    mode_mix = {
        "two_wheeler": 0.546,
        "three_wheeler": 0.256,
        "car": 0.036,
        "bus": 0.162
    }
    
    all_results = {mode: [] for mode in list(mode_mix.keys()) + ['all']}
    
    for r in rates:
        print(f"Running rate {r}...")
        df = run_midblock_simulation_multimode(config, r, duration_s, mode_mix, rng)
        
        # Calculate fd
        fd_dict = flow_density_by_mode(df, 2000, 0.5, 300, 50)
        
        for mode, fd in fd_dict.items():
            if len(fd) > 1:
                # drop the first window (transient)
                fd_stable = fd.iloc[1:]
                avg_d = fd_stable['density_veh_per_km'].mean()
                avg_f = fd_stable['flow_veh_per_hr'].mean()
                all_results[mode].append((avg_d, avg_f))
                
    # Plot
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(10, 6))
    
    colors = {'two_wheeler': 'blue', 'three_wheeler': 'green', 'car': 'red', 'bus': 'purple', 'all': 'black'}
    
    for mode, data in all_results.items():
        if not data:
            continue
        d_vals, f_vals = zip(*data)
        plt.plot(d_vals, f_vals, marker='o', label=mode, color=colors[mode])
        
    plt.title("Phase 2: Multimode Fundamental Diagrams")
    plt.xlabel("Density (veh/km)")
    plt.ylabel("Flow (veh/hr)")
    plt.legend()
    plt.grid(True)
    plt.savefig('figures/phase2_fundamental_diagrams_by_mode.png', dpi=300, bbox_inches='tight')
    print("Saved to figures/phase2_fundamental_diagrams_by_mode.png")

if __name__ == "__main__":
    main()
