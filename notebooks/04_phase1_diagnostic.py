import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from src.core.vehicle import Vehicle

def accelerate(vehicles):
    for v in vehicles:
        v.speed_cells_per_step = min(
            v.max_speed_cells_per_step,
            v.speed_cells_per_step + v.max_accel_cells_per_step2
        )

def decelerate_for_gap_periodic(vehicles, road_length_cells):
    # Sort vehicles by position (highest first)
    vs = sorted(vehicles, key=lambda v: v.position_cells, reverse=True)
    
    if len(vs) < 2:
        return
        
    for i in range(len(vs)):
        follower = vs[i]
        leader = vs[i-1] # python allows i-1 = -1 for the last element!
        
        l_back = leader.position_cells - leader.length_cells + 1
        f_front = follower.position_cells
        
        gap = l_back - f_front - 1
        if i == 0:
            # follower is vs[0] (highest position), leader is vs[-1] (lowest position, wrapped)
            gap = (leader.position_cells + road_length_cells) - leader.length_cells + 1 - follower.position_cells - 1
            
        gap = max(0, gap)
        if follower.speed_cells_per_step > gap:
            follower.speed_cells_per_step = int(gap)

def randomize(vehicles, p_slowdown, rng):
    for v in vehicles:
        if v.speed_cells_per_step > 0 and rng.random() < p_slowdown:
            v.speed_cells_per_step -= 1

def update_positions_periodic(vehicles, road_length_cells):
    for v in vehicles:
        v.position_cells = (v.position_cells + v.speed_cells_per_step) % road_length_cells
    return vehicles

def run_diagnostic():
    road_length_cells = 2000
    car_length = 7
    car_max_speed = 28
    car_max_accel = 3
    p_slowdown = 0.06
    
    rng = np.random.default_rng(42)
    
    # max possible N:
    max_N = road_length_cells // car_length
    
    densities = []
    flows = []
    
    Ns = list(range(1, max_N, max(1, max_N // 40)))
    
    for N in Ns:
        # Place N cars evenly spaced
        spacing = road_length_cells // N
        vehicles = []
        for i in range(N):
            pos = i * spacing + car_length - 1
            v = Vehicle(
                id=i, mode="car", length_cells=car_length, width_cells=3,
                max_speed_cells_per_step=car_max_speed, max_accel_cells_per_step2=car_max_accel,
                position_cells=pos, lateral_position_cells=0, speed_cells_per_step=0
            )
            vehicles.append(v)
            
        # Warmup
        for _ in range(500):
            accelerate(vehicles)
            decelerate_for_gap_periodic(vehicles, road_length_cells)
            randomize(vehicles, p_slowdown, rng)
            vehicles = update_positions_periodic(vehicles, road_length_cells)
            
        # Measurement
        measure_steps = 500
        total_distance = 0
        for _ in range(measure_steps):
            accelerate(vehicles)
            decelerate_for_gap_periodic(vehicles, road_length_cells)
            randomize(vehicles, p_slowdown, rng)
            for v in vehicles:
                total_distance += v.speed_cells_per_step
            vehicles = update_positions_periodic(vehicles, road_length_cells)
            
        # density: veh/km
        road_km = (road_length_cells * 0.5) / 1000.0
        k = N / road_km
        
        # flow: total distance traveled / (time * length)
        # equivalently: sum of speeds = total cell-steps. 
        # average speed = total_distance / (N * measure_steps) in cells/step
        # flow = k * v
        # avg_speed_kmh = avg_speed_cells_per_step * (0.5m / 1s) * 3.6
        avg_speed_cells = total_distance / (N * measure_steps) if N > 0 else 0
        avg_speed_kmh = avg_speed_cells * 0.5 * 3.6
        q = k * avg_speed_kmh
        
        densities.append(k)
        flows.append(q)
        
    import os
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(8, 5))
    plt.plot(densities, flows, 'bo-')
    plt.title('Phase 1 Diagnostic: Periodic Boundary FD')
    plt.xlabel('Density (veh/km)')
    plt.ylabel('Flow (veh/hr)')
    plt.grid(True)
    plt.savefig('figures/phase1_diagnostic_fd.png', dpi=300)
    print("Saved Phase 1 Diagnostic plot to figures/phase1_diagnostic_fd.png")

if __name__ == "__main__":
    run_diagnostic()
