import pandas as pd
import numpy as np
from src.core.config import load_config
from src.core.vehicle import Vehicle
from src.core.motion import accelerate, decelerate_for_gap, update_positions
from src.sim.generator import generate_vehicle_arrivals
from src.core.gaps import lateral_gap
from src.core.lane_change import decide_lateral_move
from src.intersection.signal import Signal
from src.intersection.izoi import is_in_izoi, izoi_behavior

def run_debug_sim(
    config: dict, 
    rate_veh_per_hour: float, 
    duration_s: int, 
    mode_mix: dict[str, float], 
    rng: np.random.Generator
):
    cell_length_m = config['grid']['cell_length_m']
    cell_width_m = config['grid']['cell_width_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_width_m = config['midblock_test'].get('road_width_m', 7.0)
    
    road_length_cells = int(road_length_m / cell_length_m)
    road_width_cells = int(road_width_m / cell_width_m)
    stop_line_cells = road_length_cells - 100
    
    signal_config = config['signal']
    signal = Signal(
        cycle_length_s=signal_config['cycle_length_s'],
        green_s=signal_config['green_s'],
        red_s=signal_config['red_s']
    )
    
    izoi_config = config['izoi_distance_m']
    izoi_decel_rate = config['izoi_deceleration_rate']
    
    mode_params = config.get('mode_params', {})
    modes = list(mode_mix.keys())
    probs = list(mode_mix.values())
    
    arrivals = generate_vehicle_arrivals(rate_veh_per_hour, duration_s, rng)
    
    vehicles = []
    records = []
    generator_logs = []
    
    vehicle_id_counter = 1
    next_arrival_idx = 0
    pending_arrivals = []
    
    for t in range(duration_s):
        current_signal = signal.state_at(t)
        
        while next_arrival_idx < len(arrivals) and arrivals[next_arrival_idx] <= t:
            chosen_mode = rng.choice(modes, p=probs)
            pending_arrivals.append(chosen_mode)
            next_arrival_idx += 1
            
        inserted_this_step = 0
        while pending_arrivals and inserted_this_step < 10:
            mode = pending_arrivals[0]
            params = mode_params[mode]
            v_length = params['length_cells']
            v_width = params['width_cells']
            
            best_lat = -1
            best_gap = -1
            
            for lat in range(road_width_cells - v_width + 1):
                entry_clear = True
                min_back = road_length_cells
                
                for v in vehicles:
                    v_left = v.lateral_position_cells
                    v_right = v.lateral_position_cells + v.width_cells - 1
                    c_left = lat
                    c_right = lat + v_width - 1
                    
                    if c_left <= v_right and v_left <= c_right:
                        v_back = v.position_cells - v.length_cells + 1
                        if v_back <= v_length - 1:
                            entry_clear = False
                            break
                        if v_back < min_back:
                            min_back = v_back
                            
                if entry_clear:
                    gap = min_back - v_length
                    if gap > best_gap:
                        best_gap = gap
                        best_lat = lat
                        
            if best_lat >= 0:
                initial_speed = min(params['max_speed_cells_per_step'], max(0, best_gap))
                
                new_vehicle = Vehicle(
                    id=vehicle_id_counter,
                    mode=mode,
                    length_cells=v_length,
                    width_cells=v_width,
                    max_speed_cells_per_step=params['max_speed_cells_per_step'],
                    max_accel_cells_per_step2=params['max_accel_cells_per_step2'],
                    position_cells=v_length - 1,
                    lateral_position_cells=best_lat,
                    speed_cells_per_step=initial_speed
                )
                vehicles.append(new_vehicle)
                vehicle_id_counter += 1
                pending_arrivals.pop(0)
                inserted_this_step += 1
            else:
                break
                
        # Log pending arrivals
        generator_logs.append({
            "time_s": t,
            "pending_count": len(pending_arrivals),
            "inserted": inserted_this_step
        })
                
        accelerate(vehicles)
        decelerate_for_gap(vehicles)
        
        skip_randomization = set()
        for v in vehicles:
            izoi_dist_cells = int(izoi_config[v.mode] / cell_length_m)
            v_front = v.position_cells
            gap_to_stop = stop_line_cells - v_front - 1
            min_gap_izoi = v.speed_cells_per_step
            if v_front < stop_line_cells and current_signal == "red":
                actual_min_gap = min(min_gap_izoi, gap_to_stop)
            else:
                actual_min_gap = min_gap_izoi

            if is_in_izoi(v, stop_line_cells, izoi_dist_cells):
                action = izoi_behavior(v, current_signal, izoi_decel_rate, actual_min_gap)
                if action == "decelerate_izoi":
                    skip_randomization.add(v.id)
            else:
                if current_signal == "red" and v_front < stop_line_cells:
                    v.speed_cells_per_step = min(v.speed_cells_per_step, max(0, gap_to_stop))

        for v in vehicles:
            params = mode_params[v.mode]
            gaps = lateral_gap(v, vehicles)
            lat_move = decide_lateral_move(v, gaps, params['position_preference'], params['lane_change_prob'], road_width_cells, rng)
            v.lateral_position_cells += lat_move
            
        for v in vehicles:
            if v.id not in skip_randomization:
                p_slow = mode_params[v.mode]['p_slowdown']
                if v.speed_cells_per_step > 0 and rng.random() < p_slow:
                    v.speed_cells_per_step -= 1
                    
        vehicles = update_positions(vehicles, road_length_cells)
        
        for v in vehicles:
            records.append({
                "time_s": t,
                "vehicle_id": v.id,
                "position_cells": v.position_cells,
                "speed_cells_per_step": v.speed_cells_per_step,
            })
            
    return pd.DataFrame(records), pd.DataFrame(generator_logs)

def analyze_15_cycles():
    config = load_config("configs/intersection_default.yaml")
    rate_veh_per_hour = 800
    cycles = 15
    cycle_s = 130
    green_s = 30
    red_s = 100
    duration_s = cycles * cycle_s + 60
    
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(42)
    df, gen_df = run_debug_sim(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    cell_length_m = config['grid']['cell_length_m']
    road_length_cells = int(config['midblock_test']['road_length_m'] / cell_length_m)
    stop_line_cells = road_length_cells - 100
    
    # 1. Measure queue count (b): physical vehicles stopped behind stop line during red
    queue_counts = []
    for cycle in range(cycles):
        start_t = cycle * cycle_s
        red_start = start_t + green_s
        red_end = start_t + cycle_s
        
        red_df = df[(df['time_s'] >= red_start) & (df['time_s'] < red_end)]
        queued = red_df[(red_df['speed_cells_per_step'] == 0) & (red_df['position_cells'] < stop_line_cells)]
        
        q_count = 0
        if not queued.empty:
            for t, grp in queued.groupby('time_s'):
                c = len(grp['vehicle_id'].unique())
                if c > q_count:
                    q_count = c
        queue_counts.append(q_count)
        
        # Check generator backlog during the time window ~70 seconds prior (when these vehicles likely entered)
        # 1000m road / ~14m/s = ~70s travel time. So entry time is approx [red_start - 70, red_end - 70]
        entry_start = max(0, red_start - 80)
        entry_end = max(0, red_end - 50)
        period_gen = gen_df[(gen_df['time_s'] >= entry_start) & (gen_df['time_s'] < entry_end)]
        max_pending = period_gen['pending_count'].max() if not period_gen.empty else 0
        
        print(f"Cycle {cycle + 1}: Queue Count = {q_count}, Max generator pending (travel time adjusted) = {max_pending}")

    queue_counts = np.array(queue_counts)
    print(f"\nStats over {cycles} cycles:")
    print(f"Mean: {np.mean(queue_counts):.2f}")
    print(f"Std Dev: {np.std(queue_counts):.2f}")
    
    expected_mean = rate_veh_per_hour / 3600 * red_s
    print(f"Expected Mean (Poisson): {expected_mean:.2f}")
    print(f"Expected Std Dev: {np.sqrt(expected_mean):.2f}")
    
    # Also calculate the actual arrival count (a): Number of raw arrivals whose generator timestamp fell within the red window?
    # No, the red window at the stop line! The arrival time at the entry is ~70s earlier.
    # To be precise, what is the variance of raw arrivals over ANY 100s window?
    # The generator uses np.random.exponential, so the raw arrivals over 100s will have variance = mean.

if __name__ == "__main__":
    analyze_15_cycles()
