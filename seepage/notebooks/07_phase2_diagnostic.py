import os
import numpy as np
import matplotlib.pyplot as plt
from src.core.vehicle import Vehicle
from src.core.config import load_config
from src.core.gaps import front_gap, lateral_gap

def accelerate(vehicles):
    for v in vehicles:
        v.speed_cells_per_step = min(
            v.max_speed_cells_per_step,
            v.speed_cells_per_step + v.max_accel_cells_per_step2
        )

def decelerate_for_gap_periodic(vehicles, road_length_cells, road_width_cells):
    # Sort vehicles by position
    vs = sorted(vehicles, key=lambda v: v.position_cells, reverse=True)
    
    for i in range(len(vs)):
        follower = vs[i]
        
        # In 2D, gap is front_gap, but we must account for periodic boundary
        # For a true periodic 2D, we just duplicate the vehicles +road_length_cells ahead
        # Actually, simpler: compute front_gap using modulo distance
        min_gap = road_length_cells
        for j in range(len(vs)):
            if i == j: continue
            leader = vs[j]
            
            # lateral overlap check
            l_left = leader.lateral_position_cells
            l_right = leader.lateral_position_cells + leader.width_cells - 1
            f_left = follower.lateral_position_cells
            f_right = follower.lateral_position_cells + follower.width_cells - 1
            
            if f_left <= l_right and l_left <= f_right:
                # Longitudinal distance with wrap-around
                dist = leader.position_cells - follower.position_cells
                if dist < 0:
                    dist += road_length_cells
                
                gap = dist - leader.length_cells
                if gap >= 0 and gap < min_gap:
                    min_gap = gap
                    
        follower.speed_cells_per_step = min(follower.speed_cells_per_step, max(0, min_gap))

def randomize(vehicles, p_slowdown, rng):
    for v in vehicles:
        if v.speed_cells_per_step > 0 and rng.random() < p_slowdown:
            v.speed_cells_per_step -= 1

def update_positions_periodic(vehicles, road_length_cells):
    for v in vehicles:
        v.position_cells = (v.position_cells + v.speed_cells_per_step) % road_length_cells
    return vehicles

def run_diagnostic_multimode():
    config = load_config("configs/intersection_default.yaml")
    road_length_cells = 1000
    road_width_cells = 14
    p_slowdown = 0.06
    
    rng = np.random.default_rng(42)
    
    densities = []
    flows = []
    
    Ns = list(range(10, 500, 20))
    mode_mix = ['two_wheeler']*55 + ['three_wheeler']*25 + ['bus']*16 + ['car']*4
    
    for N in Ns:
        vehicles = []
        
        # Grid placement to guarantee no overlap
        # We need N vehicles placed in the grid.
        cell_size_x = 10
        cell_size_y = 2
        grid_cols = road_length_cells // cell_size_x
        grid_rows = road_width_cells // cell_size_y
        
        if N > grid_cols * grid_rows:
            break
            
        placed = 0
        for r in range(grid_rows):
            for c in range(grid_cols):
                if placed >= N: break
                mode = rng.choice(mode_mix)
                params = config['mode_params'][mode]
                
                pos_x = c * cell_size_x + params['length_cells'] - 1
                pos_y = r * cell_size_y
                
                v = Vehicle(
                    id=placed, mode=mode,
                    length_cells=params['length_cells'], width_cells=params['width_cells'],
                    max_speed_cells_per_step=params['max_speed_cells_per_step'],
                    max_accel_cells_per_step2=params['max_accel_cells_per_step2'],
                    position_cells=pos_x, lateral_position_cells=pos_y, speed_cells_per_step=0
                )
                vehicles.append(v)
                placed += 1
            if placed >= N: break
            
        # Warmup
        for _ in range(500):
            accelerate(vehicles)
            decelerate_for_gap_periodic(vehicles, road_length_cells, road_width_cells)
            
            # Simple lane change, mock without actual lane change to save time
            # Or just let them go straight since they are distributed in lanes
            
            randomize(vehicles, p_slowdown, rng)
            vehicles = update_positions_periodic(vehicles, road_length_cells)
            
        # Measurement
        measure_steps = 500
        total_distance = 0
        for _ in range(measure_steps):
            accelerate(vehicles)
            decelerate_for_gap_periodic(vehicles, road_length_cells, road_width_cells)
            randomize(vehicles, p_slowdown, rng)
            for v in vehicles:
                total_distance += v.speed_cells_per_step
            vehicles = update_positions_periodic(vehicles, road_length_cells)
            
        road_km = (road_length_cells * 0.5) / 1000.0
        k = N / road_km
        avg_speed_cells = total_distance / (N * measure_steps) if N > 0 else 0
        avg_speed_kmh = avg_speed_cells * 0.5 * 3.6
        q = k * avg_speed_kmh
        
        densities.append(k)
        flows.append(q)
        print(f"N={N}: k={k:.2f}, q={q:.2f}")
        
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(8, 5))
    plt.plot(densities, flows, 'bo-')
    plt.title('Phase 2 Diagnostic: Periodic Multimode FD')
    plt.xlabel('Density (veh/km)')
    plt.ylabel('Flow (veh/hr)')
    plt.grid(True)
    plt.savefig('figures/phase2_diagnostic_fd.png', dpi=300)
    print("Saved to figures/phase2_diagnostic_fd.png")

if __name__ == "__main__":
    run_diagnostic_multimode()
