"""
Phase 4 Starvation/Deadlock check.
Proper per-vehicle measurement: for each right-turning vehicle, measure 
the time from when it first stops behind the stop line to when it crosses it.
"""
import numpy as np
import time
from src.core.config import load_config
from src.intersection.intersection import Intersection

def run_starvation_check(rate, cycles=15):
    print(f'Running starvation check for {rate} veh/hr over {cycles} cycles...', flush=True)
    config = load_config('configs/intersection_default.yaml')
    duration_s = cycles * config['signal']['cycle_length_s']
    mode_mix = {'two_wheeler': 0.546, 'car': 0.267, 'three_wheeler': 0.151, 'bus': 0.036}
    rng = np.random.default_rng(42)
    inter = Intersection(config, rate, duration_s, mode_mix, rng)
    
    # Per-vehicle: track when they FIRST appear stopped within 200 cells of stop line (right-turning)
    first_stop_t = {}  # v_id -> first timestep seen within 200 cells of stop, stopped, right-turning
    crossed_wait = []  # wait time (s) for each right-turner that eventually crossed
    still_waiting = {}  # v_id -> wait time for those that never crossed
    
    t0 = time.time()
    for t in range(duration_s):
        inter.step(t)
        for leg in inter.legs:
            for v in leg.vehicles:
                turn = leg.turn_directions.get(v.id)
                if turn != 'right':
                    continue
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past >= 0:
                    # Vehicle crossed! Record wait if we tracked it
                    if v.id in first_stop_t:
                        crossed_wait.append(t - first_stop_t.pop(v.id))
                elif -200 < pos_past < 0:
                    # Behind stop line - start tracking on first observation
                    if v.id not in first_stop_t:
                        first_stop_t[v.id] = t

    # Remaining vehicles never crossed
    for v_id, start_t in first_stop_t.items():
        still_waiting[v_id] = duration_s - start_t

    elapsed = time.time() - t0
    n_crossed = len(crossed_wait)
    n_stuck = len(still_waiting)
    max_wait_crossed = max(crossed_wait) if crossed_wait else 0
    max_wait_stuck = max(still_waiting.values()) if still_waiting else 0
    
    print(f'  Elapsed: {elapsed:.1f}s')
    print(f'  Right-turners that crossed stop line: {n_crossed}')
    print(f'  Right-turners still waiting at end: {n_stuck}')
    print(f'  Max wait (crossed vehicles): {max_wait_crossed}s')
    print(f'  Max wait (stuck vehicles, lower bound): {max_wait_stuck}s')
    if crossed_wait:
        print(f'  Mean wait (crossed): {sum(crossed_wait)/len(crossed_wait):.1f}s')
    
    return max_wait_crossed, max_wait_stuck

if __name__ == "__main__":
    max_c, max_s = run_starvation_check(1200, 15)
    print()
    max_c2, max_s2 = run_starvation_check(2000, 15)
