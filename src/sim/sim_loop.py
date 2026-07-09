import pandas as pd
import numpy as np
from src.core.vehicle import Vehicle
from src.core.motion import accelerate, decelerate_for_gap, randomize, update_positions
from src.sim.generator import generate_vehicle_arrivals
from src.core.gaps import lateral_gap
from src.core.lane_change import decide_lateral_move

def run_midblock_simulation(config: dict, rate_veh_per_hour: float, duration_s: int, rng: np.random.Generator) -> pd.DataFrame:
    """
    Runs the Phase 1 midblock simulation.
    """
    cell_length_m = config['grid']['cell_length_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_length_cells = int(road_length_m / cell_length_m)
    
    arrivals = generate_vehicle_arrivals(rate_veh_per_hour, duration_s, rng)
    
    vehicles = []
    records = []
    
    vehicle_id_counter = 1
    next_arrival_idx = 0
    pending_arrivals = 0
    
    car_length = 7
    car_max_speed = 28
    car_max_accel = 3
    p_slowdown = 0.06
    
    for t in range(duration_s):
        while next_arrival_idx < len(arrivals) and arrivals[next_arrival_idx] <= t:
            pending_arrivals += 1
            next_arrival_idx += 1
            
        if pending_arrivals > 0:
            entry_clear = True
            min_back = road_length_cells
            for v in vehicles:
                v_back = v.position_cells - v.length_cells + 1
                if v_back <= car_length - 1:
                    entry_clear = False
                    break
                if v_back < min_back:
                    min_back = v_back
                    
            if entry_clear:
                gap = min_back - car_length
                initial_speed = min(car_max_speed, max(0, gap))
                
                new_vehicle = Vehicle(
                    id=vehicle_id_counter,
                    mode="car",
                    length_cells=car_length,
                    width_cells=3,
                    max_speed_cells_per_step=car_max_speed,
                    max_accel_cells_per_step2=car_max_accel,
                    position_cells=car_length - 1,
                    lateral_position_cells=0,
                    speed_cells_per_step=initial_speed
                )
                vehicles.append(new_vehicle)
                vehicle_id_counter += 1
                pending_arrivals -= 1
                
        accelerate(vehicles)
        decelerate_for_gap(vehicles)
        randomize(vehicles, p_slowdown, rng)
        vehicles = update_positions(vehicles, road_length_cells)
        
        for v in vehicles:
            records.append({
                "time_s": t,
                "vehicle_id": v.id,
                "position_cells": v.position_cells,
                "speed_cells_per_step": v.speed_cells_per_step
            })
            
    df = pd.DataFrame(records)
    return df

def run_midblock_simulation_multimode(
    config: dict, 
    rate_veh_per_hour: float, 
    duration_s: int, 
    mode_mix: dict[str, float], 
    rng: np.random.Generator
) -> pd.DataFrame:
    """
    Runs the Phase 2 multimode 2D simulation.
    """
    if not np.isclose(sum(mode_mix.values()), 1.0):
        raise ValueError("mode_mix proportions must sum to 1.0")
        
    cell_length_m = config['grid']['cell_length_m']
    cell_width_m = config['grid']['cell_width_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_width_m = config['midblock_test'].get('road_width_m', 7.0) # default to 7m (2 lanes)
    road_length_cells = int(road_length_m / cell_length_m)
    road_width_cells = int(road_width_m / cell_width_m)
    
    mode_params = config.get('mode_params', {})
    modes = list(mode_mix.keys())
    probs = list(mode_mix.values())
    
    arrivals = generate_vehicle_arrivals(rate_veh_per_hour, duration_s, rng)
    
    vehicles = []
    records = []
    
    vehicle_id_counter = 1
    next_arrival_idx = 0
    pending_arrivals = []
    
    for t in range(duration_s):
        while next_arrival_idx < len(arrivals) and arrivals[next_arrival_idx] <= t:
            chosen_mode = rng.choice(modes, p=probs)
            pending_arrivals.append(chosen_mode)
            next_arrival_idx += 1
            
        inserted_this_step = 0
        while pending_arrivals and inserted_this_step < 10: # prevent infinite loop, max 10 per step
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
                # If the very first vehicle cannot fit anywhere, we must stop inserting this second!
                # Since it's a FIFO queue, we do not skip.
                break
                
        # 1. Accelerate
        accelerate(vehicles)
        
        # 2. Decelerate for gap
        decelerate_for_gap(vehicles)
        
        # 3. Lateral Move
        for v in vehicles:
            params = mode_params[v.mode]
            gaps = lateral_gap(v, vehicles)
            lat_move = decide_lateral_move(
                v, gaps, 
                params['position_preference'], 
                params['lane_change_prob'], 
                road_width_cells, 
                rng
            )
            v.lateral_position_cells += lat_move
            
        # 4. Randomize
        # We need per-vehicle p_slowdown!
        for v in vehicles:
            p_slow = mode_params[v.mode]['p_slowdown']
            if v.speed_cells_per_step > 0 and rng.random() < p_slow:
                v.speed_cells_per_step -= 1
                
        # 5. Update positions
        vehicles = update_positions(vehicles, road_length_cells)
        
        # Log states
        for v in vehicles:
            records.append({
                "time_s": t,
                "vehicle_id": v.id,
                "mode": v.mode,
                "position_cells": v.position_cells,
                "lateral_position_cells": v.lateral_position_cells,
                "speed_cells_per_step": v.speed_cells_per_step
            })
            
    df = pd.DataFrame(records)
    return df
import os
import pandas as pd
import numpy as np
from src.core.vehicle import Vehicle
from src.core.motion import accelerate, decelerate_for_gap, update_positions
from src.sim.generator import generate_vehicle_arrivals
from src.core.gaps import lateral_gap
from src.core.lane_change import decide_lateral_move
from src.intersection.signal import Signal
from src.intersection.izoi import is_in_izoi, izoi_behavior

def run_single_leg_with_signal(
    config: dict, 
    rate_veh_per_hour: float, 
    duration_s: int, 
    mode_mix: dict[str, float], 
    rng: np.random.Generator
) -> pd.DataFrame:
    
    if not np.isclose(sum(mode_mix.values()), 1.0):
        raise ValueError("mode_mix proportions must sum to 1.0")
        
    cell_length_m = config['grid']['cell_length_m']
    cell_width_m = config['grid']['cell_width_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_width_m = config['midblock_test'].get('road_width_m', 7.0)
    
    # We place the intersection stop line at the end of the road section
    road_length_cells = int(road_length_m / cell_length_m)
    road_width_cells = int(road_width_m / cell_width_m)
    stop_line_cells = road_length_cells - 100 # Stop line is 50m before the end
    
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
                
        # 1. Accelerate
        accelerate(vehicles)
        
        # 2. Decelerate for gap (vehicle-to-vehicle)
        decelerate_for_gap(vehicles)
        
        # 3. IZOI Behavior and Randomization preparation
        skip_randomization = set()
        for v in vehicles:
            izoi_dist_m = izoi_config[v.mode]
            izoi_dist_cells = int(izoi_dist_m / cell_length_m)
            
            # Find gap to vehicle ahead or stop line
            v_front = v.position_cells
            gap_to_stop = stop_line_cells - v_front - 1
            
            # We must consider if the vehicle is BEFORE the stop line.
            # If past stop line, no stop line gap applies.
            min_gap_izoi = v.speed_cells_per_step # Start with whatever decelerate_for_gap gave
            if v_front < stop_line_cells and current_signal == "red":
                # Ensure gap doesn't exceed stop line distance
                # But wait, decelerate_for_gap already limited speed based on vehicles.
                # So we just need to ensure we don't hit the stop line.
                actual_min_gap = min(min_gap_izoi, gap_to_stop)
            else:
                actual_min_gap = min_gap_izoi

            if is_in_izoi(v, stop_line_cells, izoi_dist_cells):
                action = izoi_behavior(v, current_signal, izoi_decel_rate, actual_min_gap)
                if action == "decelerate_izoi":
                    skip_randomization.add(v.id)
            else:
                # If not in IZOI, but red signal, we STILL should not cross the stop line if we happen to reach it
                # Wait, if outside IZOI, they behave midblock. But they shouldn't run a red light just because IZOI is short!
                # Actually, IZOI is exactly the threshold where they START reacting.
                # So before IZOI, they just drive normally. But we must enforce not crossing the red light!
                # The rule is: decelerate at field_decel_rate *when in IZOI*.
                # If they are very close (inside IZOI), they brake.
                # The assumption is IZOI is large enough to stop safely.
                if current_signal == "red" and v_front < stop_line_cells:
                    # Hard enforcement to not run red light if they somehow reach it
                    v.speed_cells_per_step = min(v.speed_cells_per_step, max(0, gap_to_stop))

        # 4. Lateral Move
        for v in vehicles:
            params = mode_params[v.mode]
            gaps = lateral_gap(v, vehicles)
            lat_move = decide_lateral_move(
                v, gaps, 
                params['position_preference'], 
                params['lane_change_prob'], 
                road_width_cells, 
                rng
            )
            v.lateral_position_cells += lat_move
            
        # 5. Randomize
        for v in vehicles:
            if v.id not in skip_randomization:
                p_slow = mode_params[v.mode]['p_slowdown']
                if v.speed_cells_per_step > 0 and rng.random() < p_slow:
                    v.speed_cells_per_step -= 1
                    
        # 6. Update positions
        vehicles = update_positions(vehicles, road_length_cells)
        
        # Log states
        for v in vehicles:
            records.append({
                "time_s": t,
                "vehicle_id": v.id,
                "mode": v.mode,
                "position_cells": v.position_cells,
                "lateral_position_cells": v.lateral_position_cells,
                "speed_cells_per_step": v.speed_cells_per_step,
                "signal": current_signal,
                "pending_count": len(pending_arrivals)
            })
            
    df = pd.DataFrame(records)
    return df

def run_full_intersection(config: dict, rate_veh_per_hour: float, duration_s: int, mode_mix: dict, rng: np.random.Generator) -> pd.DataFrame:
    """
    Run a full 4-leg intersection simulation.
    """
    from src.intersection.intersection import Intersection
    
    intersection = Intersection(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    all_records = []
    for t in range(duration_s):
        records_t = intersection.step(t)
        all_records.extend(records_t)
        
    return pd.DataFrame(all_records)


def run_single_leg_with_seepage(
    config: dict,
    rate_veh_per_hour: float,
    duration_s: int,
    mode_mix: dict,
    rng: np.random.Generator,
    seepage_eligible_modes_override: list | None = None,
) -> pd.DataFrame:
    """
    Single-leg simulation with Phase 5 seepage wired in.

    For vehicles where is_seepage_eligible() is True, attempt_seepage() is called
    INSTEAD of the plain IZOI-red deceleration branch (seepage is a more specific
    case of "in IZOI and red" — the eligibility check already implies that condition).

    Records include a `seepage_action` column:
      - "seep_left" | "seep_right" | "seep_diagonal" | "stopped"  for eligible vehicles
      - None for non-eligible vehicles/timesteps

    Parameters
    ----------
    seepage_eligible_modes_override : list or None
        If provided, overrides config['seepage_eligible_modes'].
        Pass [] to disable seepage entirely (validation: seepage-off run).
        Pass None to use config value (default).
    """
    from src.intersection.signal import Signal
    from src.intersection.izoi import is_in_izoi, izoi_behavior
    from src.intersection.seepage import is_seepage_eligible, attempt_seepage

    if not np.isclose(sum(mode_mix.values()), 1.0):
        raise ValueError("mode_mix proportions must sum to 1.0")

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
        red_s=signal_config['red_s'],
    )

    izoi_config = config['izoi_distance_m']
    izoi_decel_rate = config['izoi_deceleration_rate']

    # Seepage config — allow override for seepage-on vs seepage-off comparison
    seepage_eligible_modes = (
        seepage_eligible_modes_override
        if seepage_eligible_modes_override is not None
        else config.get('seepage_eligible_modes', ['two_wheeler', 'three_wheeler'])
    )

    mode_params = config.get('mode_params', {})
    modes = list(mode_mix.keys())
    probs = list(mode_mix.values())

    arrivals = generate_vehicle_arrivals(rate_veh_per_hour, duration_s, rng)

    vehicles: list[Vehicle] = []
    records = []

    vehicle_id_counter = 1
    next_arrival_idx = 0
    pending_arrivals: list[str] = []

    for t in range(duration_s):
        current_signal = signal.state_at(t)

        # Vehicle generation
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
                    speed_cells_per_step=initial_speed,
                )
                vehicles.append(new_vehicle)
                vehicle_id_counter += 1
                pending_arrivals.pop(0)
                inserted_this_step += 1
            else:
                break

        # 1. Accelerate
        accelerate(vehicles)
        # 2. Decelerate for gap
        decelerate_for_gap(vehicles)

        # 3. IZOI behavior / Seepage (replaces plain IZOI-red stop for eligible vehicles)
        skip_randomization: set[int] = set()
        seepage_actions: dict[int, str | None] = {}
        # Shared cell-occupancy set for this timestep's seepage moves.
        # Pre-populated with the full footprints of all existing vehicles so seeping
        # vehicles cannot overlap with stationary non-seeping vehicles.
        # Also accumulates cells claimed by seeping vehicles this timestep.
        seepage_occupied: set[tuple[int, int]] = set()
        for v in vehicles:
            for x in range(v.position_cells - v.length_cells + 1, v.position_cells + 1):
                for y in range(v.lateral_position_cells, v.lateral_position_cells + v.width_cells):
                    seepage_occupied.add((x, y))

        for v in vehicles:
            izoi_dist_m = izoi_config[v.mode]
            izoi_dist_cells = int(izoi_dist_m / cell_length_m)

            v_front = v.position_cells
            gap_to_stop = stop_line_cells - v_front - 1
            min_gap_izoi = v.speed_cells_per_step
            if v_front < stop_line_cells and current_signal == "red":
                actual_min_gap = min(min_gap_izoi, gap_to_stop)
            else:
                actual_min_gap = min_gap_izoi

            # Check seepage eligibility FIRST (more specific case of IZOI+red)
            if is_seepage_eligible(
                v,
                current_signal,
                stop_line_cells,
                izoi_dist_cells,
                seepage_eligible_modes,
            ):
                # attempt_seepage handles both successful seeps AND the stopped fallback.
                # Pass seepage_occupied so simultaneous seeps to the same cell are blocked.
                action = attempt_seepage(
                    v, vehicles, config, int(izoi_decel_rate), stop_line_cells, rng,
                    occupied_cells=seepage_occupied,
                )
                seepage_actions[v.id] = action
                skip_randomization.add(v.id)  # No randomization during seepage
            elif is_in_izoi(v, stop_line_cells, izoi_dist_cells):
                action_izoi = izoi_behavior(v, current_signal, int(izoi_decel_rate), actual_min_gap)
                if action_izoi == "decelerate_izoi":
                    skip_randomization.add(v.id)
                seepage_actions[v.id] = None
            else:
                seepage_actions[v.id] = None
                if current_signal == "red" and v_front < stop_line_cells:
                    v.speed_cells_per_step = min(v.speed_cells_per_step, max(0, gap_to_stop))


        # 4. Lateral Move (only for non-seeping vehicles ahead of stop line)
        for v in vehicles:
            if v.position_cells < stop_line_cells and seepage_actions.get(v.id) not in ("seep_left", "seep_right"):
                params = mode_params[v.mode]
                gaps = lateral_gap(v, vehicles)
                lat_move = decide_lateral_move(
                    v, gaps,
                    params['position_preference'],
                    params['lane_change_prob'],
                    road_width_cells,
                    rng,
                )
                v.lateral_position_cells += lat_move

        # 5. Randomize (skip for IZOI-decelerating and seeping vehicles)
        for v in vehicles:
            if v.id not in skip_randomization:
                p_slow = mode_params[v.mode]['p_slowdown']
                if v.speed_cells_per_step > 0 and rng.random() < p_slow:
                    v.speed_cells_per_step -= 1

        # 6. Update positions
        # To prevent double-movement of seeping vehicles (whose position was directly updated
        # in attempt_seepage), we temporarily store their speed, set it to 0 for update_positions,
        # and then restore it for correct logging and downstream velocity calculations.
        original_speeds = {}
        for v in vehicles:
            if seepage_actions.get(v.id) in ("seep_left", "seep_right", "seep_diagonal"):
                original_speeds[v.id] = v.speed_cells_per_step
                v.speed_cells_per_step = 0

        vehicles = update_positions(vehicles, road_length_cells)

        for v in vehicles:
            if v.id in original_speeds:
                v.speed_cells_per_step = original_speeds[v.id]

        # Log states
        for v in vehicles:
            records.append({
                "time_s": t,
                "vehicle_id": v.id,
                "mode": v.mode,
                "position_cells": v.position_cells,
                "lateral_position_cells": v.lateral_position_cells,
                "speed_cells_per_step": v.speed_cells_per_step,
                "signal": current_signal,
                "seepage_action": seepage_actions.get(v.id),
                "pending_count": len(pending_arrivals),
            })

    return pd.DataFrame(records)
