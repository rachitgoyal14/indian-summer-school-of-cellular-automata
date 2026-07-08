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
    
    rates = [500, 1000, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 25000, 30000]
    duration_s = 1000
    rng = np.random.default_rng(42)
    
    modes = ['two_wheeler', 'three_wheeler', 'car', 'bus']
    all_results = {mode: [] for mode in modes}
    
    for target_mode in modes:
        print(f"Running pure {target_mode}...")
        # 100% of the target mode
        mode_mix = {m: (1.0 if m == target_mode else 0.0) for m in modes}
        
        for r in rates:
            df = run_midblock_simulation_multimode(config, r, duration_s, mode_mix, rng)
            fd_dict = flow_density_by_mode(df, 2000, 0.5, 200, 50)
            
            # The result is in fd_dict['all'] or fd_dict[target_mode]
            fd = fd_dict['all']
            if len(fd) > 1:
                fd_stable = fd.iloc[1:]
                avg_d = fd_stable['density_veh_per_km'].mean()
                avg_f = fd_stable['flow_veh_per_hr'].mean()
                all_results[target_mode].append((avg_d, avg_f))
                
    # Plot
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(10, 6))
    
    colors = {'two_wheeler': 'blue', 'three_wheeler': 'green', 'car': 'red', 'bus': 'purple'}
    
    for mode, data in all_results.items():
        if not data:
            continue
        d_vals, f_vals = zip(*data)
        plt.plot(d_vals, f_vals, marker='o', label=mode, color=colors[mode])
        
    plt.title("Phase 2: Isolated Mode Capacities (100% single-mode sweeps)")
    plt.xlabel("Density (veh/km)")
    plt.ylabel("Flow (veh/hr)")
    plt.legend()
    plt.grid(True)
    plt.savefig('figures/phase2_isolated_capacities.png', dpi=300, bbox_inches='tight')
    print("Saved to figures/phase2_isolated_capacities.png")

    # Print peak capacities
    print("\nPeak Capacities in Isolation:")
    for mode, data in all_results.items():
        if not data: continue
        peak = max([x[1] for x in data])
        print(f"{mode}: {peak:.2f} veh/hr")

if __name__ == "__main__":
    main()
