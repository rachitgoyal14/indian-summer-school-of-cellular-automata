import numpy as np
import time
from src.core.config import load_config
from src.intersection.intersection import Intersection

def run_fast_starvation(rate, cycles=15):
    print(f"Running fast starvation check for {rate} veh/hr over {cycles} cycles...", flush=True)
    config = load_config('configs/intersection_default.yaml')
    duration_s = cycles * config['signal']['cycle_length_s']
    
    mode_mix = {'two_wheeler': 0.546, 'car': 0.267, 'three_wheeler': 0.151, 'bus': 0.036}
    rng = np.random.default_rng(42)
    
    inter = Intersection(config, rate, duration_s, mode_mix, rng)
    
    start_t = time.time()
    
    wait_times = {}
    max_wait = 0
    
    for t in range(duration_s):
        inter.step(t)
        
        # Track vehicles waiting behind the stop line
        for leg in inter.legs:
            for v in leg.vehicles:
                turn = leg.turn_directions[v.id]
                if turn == 'right':
                    pos_past = v.position_cells - leg.stop_line_position_cells
                    if -100 < pos_past <= 0 and v.speed_cells_per_step == 0:
                        if v.id not in wait_times:
                            wait_times[v.id] = 0
                        wait_times[v.id] += 1
                        if wait_times[v.id] > max_wait:
                            max_wait = wait_times[v.id]
                    elif pos_past > 0:
                        # Exited the queue
                        pass
        
        if t % 100 == 0:
            pass
            
    print(f"Done in {time.time() - start_t:.2f}s", flush=True)
    print(f"Max wait time for right-turning vehicle at {rate} veh/hr: {max_wait} seconds", flush=True)

if __name__ == "__main__":
    run_fast_starvation(1200, 15)
    run_fast_starvation(2400, 15)
