import pandas as pd
import numpy as np
from src.core.vehicle import Vehicle
from src.core.motion import accelerate, decelerate_for_gap, randomize, update_positions
from src.sim.generator import generate_vehicle_arrivals

def run_midblock_simulation(config: dict, rate_veh_per_hour: float, duration_s: int, rng: np.random.Generator) -> pd.DataFrame:
    """
    Runs the Phase 1 midblock simulation.
    Returns a DataFrame with columns: time_s, vehicle_id, position_cells, speed_cells_per_step
    """
    cell_length_m = config['grid']['cell_length_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_length_cells = int(road_length_m / cell_length_m)
    
    arrivals = generate_vehicle_arrivals(rate_veh_per_hour, duration_s, rng)
    
    vehicles = []
    records = []
    
    vehicle_id_counter = 1
    next_arrival_idx = 0
    
    # Waiting queue for vehicles that have arrived but cannot enter yet
    pending_arrivals = 0
    
    # Test params for forcing jam
    car_length = 7
    car_max_speed = 28
    car_max_accel = 3
    p_slowdown = 0.06
    
    for t in range(duration_s):
        # Check for new arrivals at this second
        while next_arrival_idx < len(arrivals) and arrivals[next_arrival_idx] <= t:
            pending_arrivals += 1
            next_arrival_idx += 1
            
        # Try to insert waiting vehicles
        if pending_arrivals > 0:
            # Check if entry is clear (front of a new vehicle would be at car_length - 1)
            # The new vehicle occupies cells 0 to car_length - 1
            entry_clear = True
            min_back = road_length_cells
            for v in vehicles:
                # If any vehicle's back is <= car_length - 1, the entry is blocked
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
                    max_speed_cells_per_step=car_max_speed,
                    max_accel_cells_per_step2=car_max_accel,
                    position_cells=car_length - 1, # front bumper
                    speed_cells_per_step=initial_speed
                )
                vehicles.append(new_vehicle)
                vehicle_id_counter += 1
                pending_arrivals -= 1
                
        # CA Steps
        accelerate(vehicles)
        decelerate_for_gap(vehicles)
        randomize(vehicles, p_slowdown, rng)
        vehicles = update_positions(vehicles, road_length_cells)
        
        # Log states
        for v in vehicles:
            records.append({
                "time_s": t,
                "vehicle_id": v.id,
                "position_cells": v.position_cells,
                "speed_cells_per_step": v.speed_cells_per_step
            })
            
    df = pd.DataFrame(records)
    return df
