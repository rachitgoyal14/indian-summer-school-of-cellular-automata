import os
import numpy as np
import matplotlib.pyplot as plt
from src.core.vehicle import Vehicle
from src.core.config import load_config
from src.core.gaps import front_gap

def accelerate(vehicles):
    for v in vehicles:
        v.speed_cells_per_step = min(
            v.max_speed_cells_per_step,
            v.speed_cells_per_step + v.max_accel_cells_per_step2
        )

def decelerate_for_gap_open(vehicles, road_length_cells):
    # Sort vehicles by position (highest position first)
    vs = sorted(vehicles, key=lambda v: v.position_cells, reverse=True)
    
    for i in range(len(vs)):
        follower = vs[i]
        
        # In single lane open road, leader is the next vehicle ahead
        if i == 0:
            # First vehicle sees open road ahead
            min_gap = road_length_cells
        else:
            leader = vs[i-1]
            min_gap = leader.position_cells - follower.position_cells - leader.length_cells
            
        follower.speed_cells_per_step = min(follower.speed_cells_per_step, max(0, min_gap))

def randomize(vehicles, p_slowdown, rng):
    for v in vehicles:
        if v.speed_cells_per_step > 0 and rng.random() < p_slowdown:
            v.speed_cells_per_step -= 1

def update_positions_open(vehicles):
    for v in vehicles:
        v.position_cells += v.speed_cells_per_step
    return vehicles

def run_diagnostic_open():
    config = load_config("configs/intersection_default.yaml")
    road_length_cells = 2000
    p_slowdown = 0.06
    
    rng = np.random.default_rng(42)
    
    densities = []
    flows = []
    
    # We test up to max possible packing
    params = config['mode_params']['car']
    car_len = params['length_cells']
    max_N = road_length_cells // (car_len + 1)
    
    Ns = list(range(10, max_N, 10))
    
    for N in Ns:
        vehicles = []
        # Place N vehicles tightly packed near the start of the road
        for i in range(N):
            pos_x = i * (car_len + 1) + car_len - 1
            v = Vehicle(
                id=i, mode='car',
                length_cells=car_len, width_cells=params['width_cells'],
                max_speed_cells_per_step=params['max_speed_cells_per_step'],
                max_accel_cells_per_step2=params['max_accel_cells_per_step2'],
                position_cells=pos_x, lateral_position_cells=0, speed_cells_per_step=0
            )
            vehicles.append(v)
            
        # Warmup (only 50 steps so they don't all exit!)
        for _ in range(50):
            accelerate(vehicles)
            decelerate_for_gap_open(vehicles, road_length_cells)
            randomize(vehicles, p_slowdown, rng)
            vehicles = update_positions_open(vehicles)
            # Remove exited
            vehicles = [v for v in vehicles if v.position_cells < road_length_cells]
            
        # Measurement window (100 steps)
        measure_steps = 100
        total_distance = 0
        active_veh_count = 0
        
        for _ in range(measure_steps):
            accelerate(vehicles)
            decelerate_for_gap_open(vehicles, road_length_cells)
            randomize(vehicles, p_slowdown, rng)
            for v in vehicles:
                total_distance += v.speed_cells_per_step
            vehicles = update_positions_open(vehicles)
            vehicles = [v for v in vehicles if v.position_cells < road_length_cells]
            active_veh_count += len(vehicles)
            
        # Average density during measurement
        avg_vehicles = active_veh_count / measure_steps
        road_km = (road_length_cells * 0.5) / 1000.0
        k = avg_vehicles / road_km
        
        avg_speed_cells = total_distance / active_veh_count if active_veh_count > 0 else 0
        avg_speed_kmh = avg_speed_cells * 0.5 * 3.6
        q = k * avg_speed_kmh
        
        densities.append(k)
        flows.append(q)
        print(f"Initial N={N}: k={k:.2f}, q={q:.2f}")
        
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(8, 5))
    plt.plot(densities, flows, 'bo-')
    plt.title('Phase 1 Diagnostic: Open Boundary FD')
    plt.xlabel('Average Density during Measurement (veh/km)')
    plt.ylabel('Flow (veh/hr)')
    plt.grid(True)
    plt.savefig('figures/phase1_open_diagnostic_fd.png', dpi=300)
    print("Saved to figures/phase1_open_diagnostic_fd.png")

if __name__ == "__main__":
    run_diagnostic_open()
