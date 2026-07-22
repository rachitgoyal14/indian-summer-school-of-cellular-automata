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
    
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # 1. Plot the road geometry lines to define the global frame
    ax.plot([0, W], [W, W], 'k-', lw=2) # West leg top
    ax.plot([0, W], [2*W, 2*W], 'k-', lw=2) # West leg bottom
    ax.plot([W, W], [2*W, 4*W], 'k-', lw=2) # North leg left
    ax.plot([2*W, 2*W], [2*W, 4*W], 'k-', lw=2) # North leg right
    ax.plot([2*W, 4*W], [2*W, 2*W], 'k-', lw=2) # East leg bottom
    ax.plot([2*W, 4*W], [W, W], 'k-', lw=2) # East leg top
    ax.plot([W, W], [0, W], 'k-', lw=2) # South leg left
    ax.plot([2*W, 2*W], [0, W], 'k-', lw=2) # South leg right
    # Junction box
    ax.plot([W, 2*W, 2*W, W, W], [W, W, 2*W, 2*W, W], 'k--', alpha=0.5)
    
    # Track which turns we've highlighted
    highlighted = {'left': 0, 'right': 0}
    
    for leg_id in range(4):
        leg_df = df[df['leg_origin'] == leg_id]
        
        for v_id, grp in leg_df.groupby('vehicle_id'):
            grp = grp.sort_values('time_s')
            if grp.empty:
                continue
                
            turn = grp.iloc[0]['turn']
            is_highlight = False
            
            # Select a few vehicles to highlight
            if turn == 'left' and highlighted['left'] < 2:
                is_highlight = True
                highlighted['left'] += 1
            elif turn == 'right' and highlighted['right'] < 2:
                is_highlight = True
                highlighted['right'] += 1
                
            if is_highlight:
                ax.plot(grp['x'], grp['y'], color='magenta', alpha=1.0, linewidth=3, zorder=5)
                ax.scatter(grp['x'], grp['y'], color='black', s=15, zorder=6)
                # Annotate start and end
                ax.text(grp['x'].iloc[0], grp['y'].iloc[0], f"Start {turn}", fontsize=8, color='magenta')
                ax.text(grp['x'].iloc[-1], grp['y'].iloc[-1], f"End {turn}", fontsize=8, color='magenta')
            else:
                ax.plot(grp['x'], grp['y'], color=color_map[leg_id], alpha=0.1, linewidth=1)
                
    ax.set_title('Global Intersection Trajectories (Single View)')
    ax.set_xlabel('Global X (cells)')
    ax.set_ylabel('Global Y (cells)')
    ax.set_xlim(-50, 4*W + 50)
    ax.set_ylim(-50, 4*W + 50)
    ax.grid(True)
        
    plt.tight_layout()
    plt.savefig('figures/phase4_full_intersection_trajectories_single.png')

if __name__ == "__main__":
    plot_intersection_trajectories()
