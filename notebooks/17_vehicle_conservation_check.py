"""
Verify vehicle conservation:
For a fixed window (15 cycles = 1950 seconds):
total_generated == exited_naturally + forced_through + (vehicles still on road + vehicles in entry backlog)
"""
import numpy as np
from src.core.config import load_config
from src.intersection.intersection import Intersection

def run_conservation_check(rate, cycles=15):
    print(f"Running vehicle conservation check for {rate} veh/hr over {cycles} cycles...")
    config = load_config('configs/intersection_default.yaml')
    duration_s = cycles * config['signal']['cycle_length_s']
    mode_mix = {'two_wheeler': 0.546, 'car': 0.267, 'three_wheeler': 0.151, 'bus': 0.036}
    rng = np.random.default_rng(42)
    inter = Intersection(config, rate, duration_s, mode_mix, rng)
    
    # Run the simulation
    for t in range(duration_s):
        inter.step(t)
        
    # Count variables
    exited_naturally = inter.natural_exits_count
    forced_through = inter.forced_crossings_count
    
    # Legitimate vehicles still in system at window end:
    # 1. On the road:
    vehicles_on_road = sum(len(leg.vehicles) for leg in inter.legs)
    # 2. In entry backlog:
    vehicles_in_backlog = sum(len(leg.pending_arrivals) for leg in inter.legs)
    
    still_in_system = vehicles_on_road + vehicles_in_backlog
    
    # Total generated:
    # Every vehicle generated either got inserted (total inserted) or is still in backlog.
    # Total inserted = inter.vehicle_id_counter - 1 (since counter starts at 1)
    total_inserted = inter.vehicle_id_counter - 1
    total_generated = total_inserted + vehicles_in_backlog
    
    # Conservation check sum
    sum_right_side = exited_naturally + forced_through + still_in_system
    conserved = (total_generated == sum_right_side)
    
    print(f"  Total Generated (Backlog + Inserted): {total_generated}")
    print(f"    - Backlog: {vehicles_in_backlog}")
    print(f"    - Inserted: {total_inserted}")
    print(f"  Exited Naturally: {exited_naturally}")
    print(f"  Forced Through: {forced_through}")
    print(f"  Still on Road: {vehicles_on_road}")
    print(f"  Still in System/Queue (Backlog + On Road): {still_in_system}")
    print(f"  Sum of (Exited + Forced + Still in System): {sum_right_side}")
    print(f"  CONSERVED EXACTLY: {conserved}")
    
    # Confirm double check
    assert conserved, f"Conservation failed! {total_generated} != {sum_right_side}"
    return total_generated, exited_naturally, forced_through, still_in_system

if __name__ == "__main__":
    run_conservation_check(1200, 15)
    print()
    run_conservation_check(2000, 15)
