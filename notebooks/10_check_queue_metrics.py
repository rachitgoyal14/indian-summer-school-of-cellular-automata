import pandas as pd
import numpy as np
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_signal

def analyze_queue():
    config = load_config("configs/intersection_default.yaml")
    
    rate_veh_per_hour = 800
    duration_s = 450
    
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(42)
    df = run_single_leg_with_signal(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    cell_length_m = config['grid']['cell_length_m']
    road_length_cells = int(config['midblock_test']['road_length_m'] / cell_length_m)
    stop_line_cells = road_length_cells - 100
    
    cycle_s = 130
    green_s = 30
    red_s = 100
    
    for cycle in range(3):
        start_t = cycle * cycle_s
        red_start = start_t + green_s
        red_end = start_t + cycle_s # also next green start
        green_end = red_end + green_s
        
        # We find max queue length during red phase
        # A vehicle is in the queue if its speed is 0 and it's behind the stop line.
        # We need to find the max distance from stop line for any stopped vehicle during red.
        red_df = df[(df['time_s'] >= red_start) & (df['time_s'] < red_end)]
        queued = red_df[(red_df['speed_cells_per_step'] == 0) & (red_df['position_cells'] < stop_line_cells)]
        
        max_dist_cells = 0
        max_dist_m = 0
        queue_count = 0
        
        if not queued.empty:
            # For each time step, count how many distinct vehicles are queued and how far back it goes
            for t, grp in queued.groupby('time_s'):
                q_len = len(grp['vehicle_id'].unique())
                dist = stop_line_cells - grp['position_cells'].min()
                if q_len > queue_count:
                    queue_count = q_len
                if dist > max_dist_cells:
                    max_dist_cells = dist
                    
            max_dist_m = max_dist_cells * cell_length_m
            
        print(f"Cycle {cycle + 1} Red Phase:")
        print(f"  Max queue count: {queue_count} vehicles")
        print(f"  Max queue physical length: {max_dist_m:.1f} meters (back-calculated)")
        
        # Check if queue cleared by end of green
        # At time = green_end - 1, are there any vehicles stopped behind the stop line?
        end_green_df = df[df['time_s'] == min(green_end - 1, duration_s - 1)]
        leftover = end_green_df[(end_green_df['speed_cells_per_step'] < 5) & (end_green_df['position_cells'] < stop_line_cells)]
        # Actually, let's just check if any vehicle that was in the red queue is still behind the stop line
        red_queue_vids = queued['vehicle_id'].unique()
        leftovers = end_green_df[end_green_df['vehicle_id'].isin(red_queue_vids) & (end_green_df['position_cells'] < stop_line_cells)]
        
        if leftovers.empty:
            print(f"  Queue fully empties? YES")
        else:
            print(f"  Queue fully empties? NO ({len(leftovers)} vehicles carried over)")

if __name__ == "__main__":
    analyze_queue()
