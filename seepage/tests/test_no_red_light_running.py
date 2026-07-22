import pytest
import numpy as np
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_signal

def test_no_red_light_running():
    config = load_config("configs/intersection_default.yaml")
    # Tweak config to ensure we get a red light quickly and long enough
    config['signal']['cycle_length_s'] = 50
    config['signal']['green_s'] = 5
    config['signal']['red_s'] = 45
    
    # We want a high flow to pack the intersection
    rate_veh_per_hour = 10000
    duration_s = 40 # 5s green, 35s red
    
    # Run the simulation
    rng = np.random.default_rng(123)
    df = run_single_leg_with_signal(config, rate_veh_per_hour, duration_s, {'car': 1.0}, rng)
    
    # Stop line cells
    cell_length_m = config['grid']['cell_length_m']
    road_length_m = config['midblock_test']['road_length_m']
    road_length_cells = int(road_length_m / cell_length_m)
    stop_line_cells = road_length_cells - 100
    
    # Check if any vehicle crossed the stop line during RED
    red_df = df[df['signal'] == 'red']
    
    # "Crossed" means position_cells > stop_line_cells
    # Note: v.position_cells is the front of the vehicle.
    # Wait, the rule is the front of the vehicle must not cross the stop line.
    crossed = red_df[red_df['position_cells'] >= stop_line_cells]
    
    # BUT wait, what if they crossed during GREEN and are now past the stop line while it is RED?
    # Those vehicles are legally past the stop line.
    # We need to check if any vehicle *crossed* during red.
    # If they are past the stop line, their position should keep increasing to exit the road.
    
    # A vehicle runs a red light if its position is > stop_line_cells, AND in the previous time step it was < stop_line_cells
    # Or simply: no vehicle should have its front cross the stop_line_cells *while* the signal is red.
    
    for v_id, grp in df.groupby('vehicle_id'):
        grp = grp.sort_values('time_s')
        prev_pos = -1
        for _, row in grp.iterrows():
            pos = row['position_cells']
            sig = row['signal']
            
            # If it crossed the line this step
            if prev_pos < stop_line_cells and pos >= stop_line_cells:
                assert sig == 'green', f"Vehicle {v_id} ran a red light at time {row['time_s']}!"
            prev_pos = pos
