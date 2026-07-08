import numpy as np
import pandas as pd
from src.core.config import load_config
from src.sim.sim_loop import run_full_intersection
from src.intersection.intersection import Intersection

def run_starvation_check(rate, cycles=15):
    print(f"Running starvation check for {rate} veh/hr over {cycles} cycles...")
    config = load_config('configs/intersection_default.yaml')
    duration_s = cycles * config['signal']['cycle_length_s']
    
    mode_mix = {'two_wheeler': 0.546, 'car': 0.267, 'three_wheeler': 0.151, 'bus': 0.036}
    rng = np.random.default_rng(42)
    
    df = run_full_intersection(config, rate, duration_s, mode_mix, rng)
    
    # Calculate wait times. A vehicle is "waiting" if its speed is 0 and it is near the stop line or in the box.
    # Actually, simpler: calculate the total time a vehicle spent in the simulation before exiting.
    # And compare it to free-flow time.
    # Wait, the user specifically asked: "report the maximum single-vehicle wait time for a right-turning vehicle"
    
    # Let's define "wait time" as the time difference between entering the simulation and exiting the junction box.
    # Since they enter 1000m away, the minimum time to reach the intersection is 1000 / 28 = 35.7s.
    
    results = []
    
    for (v_id, leg), grp in df.groupby(['vehicle_id', 'leg_origin']):
        turn = grp.iloc[0]['turn']
        if turn != 'right':
            continue
            
        t_start = grp['time_s'].min()
        t_end = grp['time_s'].max()
        
        # Did it exit?
        if len(grp) > 0 and grp.iloc[-1]['position_cells'] >= 1950:
            total_time = t_end - t_start
            results.append({
                'v_id': v_id,
                'leg': leg,
                'total_time': total_time
            })
            
    if not results:
        print("No right turning vehicles finished!")
        return
        
    res_df = pd.DataFrame(results)
    max_wait = res_df['total_time'].max()
    print(f"Max time spent in system for a right-turning vehicle at {rate} veh/hr: {max_wait} seconds")
    
run_starvation_check(1200, 15)
run_starvation_check(2400, 15)
