import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_signal

def run_queue_formation():
    config = load_config("configs/intersection_default.yaml")
    
    rate_veh_per_hour = 800
    duration_s = 390 # 3 full cycles of 130s
    
    # We use a mix of vehicles to see the heterogeneous trajectories
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(42)
    df = run_single_leg_with_signal(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    cell_length_m = config['grid']['cell_length_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_length_cells = int(road_length_m / cell_length_m)
    stop_line_cells = road_length_cells - 100
    
    # Calculate saturation flow
    # Saturation flow can be estimated by looking at the discharge headway of vehicles initially queued
    # Let's find the first green phase that has a queue
    # The first green phase is 0 to 30s. The first red phase is 30 to 130s. The second green is 130 to 160s.
    # We will look at vehicles crossing the stop line between 130s and 160s.
    
    crossing_times = []
    for v_id, grp in df.groupby('vehicle_id'):
        grp = grp.sort_values('time_s')
        prev_pos = -1
        for _, row in grp.iterrows():
            pos = row['position_cells']
            if prev_pos < stop_line_cells and pos >= stop_line_cells:
                if 130 <= row['time_s'] <= 160:
                    crossing_times.append(row['time_s'])
            prev_pos = pos
            
    crossing_times.sort()
    
    if len(crossing_times) > 1:
        headways = np.diff(crossing_times)
        avg_headway = np.mean(headways)
        sat_flow = 3600 / avg_headway if avg_headway > 0 else 0
        print(f"Estimated saturation flow during green discharge: {sat_flow:.2f} veh/hr")
    else:
        print("Not enough vehicles crossed during the measured green phase to estimate saturation flow.")
    
    # Plotting
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(10, 6))
    
    # Draw red signal periods as shaded backgrounds
    # cycle is 130, green is 30, red is 100
    for t in range(0, duration_s, 130):
        # Green: t to t+30
        # Red: t+30 to t+130
        plt.axvspan(t+30, min(t+130, duration_s), facecolor='red', alpha=0.1)
    
    # We want to plot trajectory for each vehicle
    # To avoid plotting too many lines, maybe sample 100 vehicles
    sampled_vids = df['vehicle_id'].unique()[:100]
    
    color_map = {
        'two_wheeler': 'blue',
        'three_wheeler': 'green',
        'car': 'orange',
        'bus': 'purple'
    }
    
    for v_id in sampled_vids:
        v_df = df[df['vehicle_id'] == v_id]
        mode = v_df['mode'].iloc[0]
        # X is time, Y is position
        plt.plot(v_df['time_s'], v_df['position_cells'], color=color_map[mode], alpha=0.5, linewidth=1)
        
    plt.axhline(y=stop_line_cells, color='r', linestyle='--', label='Stop Line')
    
    plt.title('Phase 3: Space-Time Queue Formation and Discharge')
    plt.xlabel('Time (s)')
    plt.ylabel('Position (cells)')
    # Custom legend for modes
    from matplotlib.lines import Line2D
    custom_lines = [Line2D([0], [0], color=c, lw=2) for c in color_map.values()]
    plt.legend(custom_lines + [Line2D([0], [0], color='r', linestyle='--')], 
               list(color_map.keys()) + ['Stop Line'])
               
    plt.grid(True)
    plt.savefig('figures/phase3_queue_formation.png', dpi=300)
    print("Saved to figures/phase3_queue_formation.png")

if __name__ == "__main__":
    run_queue_formation()
