import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from src.core.config import load_config
from src.sim.sim_loop import run_full_intersection
from src.intersection.intersection import Intersection

def plot_intersection_trajectories():
    config = load_config("configs/intersection_default.yaml")
    
    rate_veh_per_hour = 1200
    duration_s = 200 # Roughly 1.5 cycles
    
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036
    }
    
    rng = np.random.default_rng(42)
    
    # We will simulate and collect records
    df = run_full_intersection(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    
    inter = Intersection(config, rate_veh_per_hour, duration_s, mode_mix, rng)
    stop_line_cells = inter.legs[0].stop_line_position_cells
    W = inter.box_size // 2
    
    # Let's map each record to a physical (x, y) coordinate for plotting
    # using the same logic as get_junction_cells, but for the whole road.
    
    mapped_x = []
    mapped_y = []
    colors = []
    
    color_map = {0: 'red', 1: 'blue', 2: 'green', 3: 'orange'}
    
    for _, row in df.iterrows():
        leg_id = row['leg_origin']
        lat_pos = row['lateral_position_cells']
        pos = row['position_cells']
        pos_past = pos - stop_line_cells
        turn = row['turn']
        
        # If it hasn't reached the junction box yet
        if pos_past < 0:
            dist_to_stop = -pos_past
            # Leg 0: x in [W, 2W-1], y = 2W + dist
            if leg_id == 0:
                x = W + lat_pos
                y = 2*W + dist_to_stop
            elif leg_id == 1:
                x = 2*W + dist_to_stop
                y = W + lat_pos
            elif leg_id == 2:
                x = lat_pos
                y = -dist_to_stop
            elif leg_id == 3:
                x = -dist_to_stop
                y = lat_pos
        else:
            # It's in the junction box (or past it, before deletion)
            # Use the front cell logic
            cells = inter.get_junction_cells(leg_id, lat_pos, turn, pos_past, 1, 1)
            if cells:
                x, y = cells[0]
            else:
                x, y = -1, -1 # Exited
                
        mapped_x.append(x)
        mapped_y.append(y)
        colors.append(color_map[leg_id])
        
    df['x'] = mapped_x
    df['y'] = mapped_y
    df['color'] = colors
    
    # Remove exited vehicles
    df = df[df['x'] != -1]
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    axes = axes.flatten()
    
    # Plot trajectories for a specific time window to avoid overwhelming clutter
    # Or plot all tracks as lines
    
    for leg_id in range(4):
        ax = axes[leg_id]
        leg_df = df[df['leg_origin'] == leg_id]
        
        for v_id, grp in leg_df.groupby('vehicle_id'):
            grp = grp.sort_values('time_s')
            ax.plot(grp['x'], grp['y'], color=color_map[leg_id], alpha=0.5, linewidth=1)
            # Draw a dot at the end
            if not grp.empty:
                ax.scatter(grp['x'].iloc[-1], grp['y'].iloc[-1], color=color_map[leg_id], s=10)
                
        # Draw the junction box
        ax.plot([0, 2*W, 2*W, 0, 0], [0, 0, 2*W, 2*W, 0], 'k--', alpha=0.5)
        
        ax.set_title(f'Trajectories from Leg {leg_id}')
        ax.set_xlabel('X (cells)')
        ax.set_ylabel('Y (cells)')
        ax.set_xlim(-100, 2*W + 100)
        ax.set_ylim(-100, 2*W + 100)
        ax.grid(True)
        
    plt.tight_layout()
    plt.savefig('figures/phase4_full_intersection_trajectories.png')

if __name__ == "__main__":
    plot_intersection_trajectories()
