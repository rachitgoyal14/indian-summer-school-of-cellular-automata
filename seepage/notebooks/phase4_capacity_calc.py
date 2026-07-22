"""
Minimal throughput diagnostic — counts box throughput per green phase
and compares Phase 3 single-leg vs Phase 4 Leg 0 behavior.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import yaml

with open("configs/intersection_default.yaml") as f:
    config = yaml.safe_load(f)

cycle_len = config['signal']['cycle_length_s']
green_len = config['signal']['green_s']
RATE = 800

print("=" * 65)
print("A. Box geometry analysis")
print("=" * 65)
from src.intersection.intersection import Intersection
dummy = Intersection(config, 100, 200, {"car": 1.0}, np.random.default_rng(0))
W = dummy.legs[0].road_width_cells
box_size = dummy.box_size
stop_line = dummy.legs[0].stop_line_position_cells
road_len = dummy.legs[0].road_length_cells
print(f"W={W}, box_size={box_size}, stop_line={stop_line}, road_len={road_len}")
print(f"Straight exit threshold: {2*box_size} cells past stop line")
print(f"At max car speed (28 cells/step): min {2*box_size/28:.1f} steps to exit box")
print(f"Expected per-green exit capacity: ~{green_len / (2*box_size/28):.0f} vehicles per leg")
print(f"Expected per-cycle arrivals at 800 veh/hr: {800 * cycle_len / 3600:.1f}")

print()
print("=" * 65)
print("B. Phase 3 behavior: how many vehicles clear stop line per cycle?")
print("=" * 65)
# Phase 3: single leg, no junction box, vehicles just drive off
# Replicate by running the run_single_leg_with_signal
from src.sim.sim_loop import run_single_leg_with_signal
import pandas as pd

rng_p3 = np.random.default_rng(42)
mode_mix = {"two_wheeler": 0.546, "three_wheeler": 0.151, "car": 0.267, "bus": 0.036}
DURATION_3CYC = 390  # 3 cycles

df_p3 = run_single_leg_with_signal(config, RATE, DURATION_3CYC, mode_mix, rng_p3)

if len(df_p3) > 0:
    # Count vehicles that crossed stop_line during each green phase
    # "crossed" = reached stop_line_cells while signal was green (then exit the road)
    # In Phase 3, road_length_cells is the exit boundary
    # But we measure queue clearing. Phase 3 has stop_line at road_length_cells - 100
    # Using the config value
    road_length_cells = int(config['midblock_test']['road_length_m'] / config['grid']['cell_length_m'])
    p3_stop_line = road_length_cells - 100
    
    print(f"Phase 3 stop line at cell {p3_stop_line}, road length {road_length_cells}")
    
    # Count vehicles queued (before stop line) at end of each green phase
    print(f"\nPhase 3 queue at end of green phase:")
    for cyc in range(3):
        t_end_green = cyc * cycle_len + green_len - 1
        if t_end_green in df_p3['time_s'].values:
            df_t = df_p3[df_p3['time_s'] == t_end_green]
            q = len(df_t[df_t['position_cells'] < p3_stop_line])
            print(f"  Cycle {cyc} (t={t_end_green}): {q} vehicles before stop line")

print()
print("=" * 65)
print("C. Phase 4 Leg 0 exits per green phase — where does it go wrong?")
print("=" * 65)

# Run 3 cycles of Phase 4 with pure car to isolate Leg 0 throughput
rng_p4 = np.random.default_rng(42)
inter = Intersection(config, RATE, DURATION_3CYC, {"car": 1.0}, rng_p4)

# Track per-step exits
exits_per_step = []
for t in range(DURATION_3CYC):
    exits_before = inter.natural_exits_count + inter.forced_crossings_count
    inter.step(t)
    exits_after = inter.natural_exits_count + inter.forced_crossings_count
    leg0 = inter.legs[0]
    q_before = sum(1 for v in leg0.vehicles if v.position_cells < leg0.stop_line_position_cells)
    in_box = sum(1 for v in leg0.vehicles if v.position_cells >= leg0.stop_line_position_cells)
    exits_per_step.append({
        't': t,
        'sig0': leg0.signal.state_at(t),
        'q_before': q_before,
        'in_box': in_box,
        'total_leg0': len(leg0.vehicles),
        'exits_this_step': exits_after - exits_before,
        'phase_in_cycle': t % cycle_len,
    })

df_ex = pd.DataFrame(exits_per_step)

# Summarize per cycle
print(f"\nPer-cycle summary (Leg 0, {DURATION_3CYC}s):")
for cyc in range(3):
    t_start = cyc * cycle_len
    t_end = min((cyc+1) * cycle_len - 1, DURATION_3CYC - 1)
    cycle_data = df_ex[(df_ex['t'] >= t_start) & (df_ex['t'] <= t_end)]
    
    green_data = cycle_data[cycle_data['sig0'] == 'green']
    red_data = cycle_data[cycle_data['sig0'] == 'red']
    
    exits_green = green_data['exits_this_step'].sum()
    exits_red = red_data['exits_this_step'].sum()
    max_q = red_data['q_before'].max() if len(red_data) > 0 else 0
    end_of_green_q = cycle_data[cycle_data['phase_in_cycle'] == green_len - 1]['q_before'].values
    eog_q = end_of_green_q[0] if len(end_of_green_q) > 0 else '?'
    in_box_max = cycle_data['in_box'].max()
    
    print(f"\n  Cycle {cyc} (t={t_start}..{t_end}):")
    print(f"    Max in-box vehicles on Leg 0: {in_box_max}")
    print(f"    Exits during green: {exits_green}")
    print(f"    Exits during red: {exits_red}")
    print(f"    Max queue (all legs' exits): {max_q} before stop")
    print(f"    Queue at end of green: {eog_q} before stop")

print(f"\nTotal all-leg exits in {DURATION_3CYC}s: {inter.natural_exits_count + inter.forced_crossings_count}")
print(f"Leg 0 vehicles inserted: {sum(1 for leg in inter.legs if leg.leg_id == 0 for v in leg.vehicles) + inter.vehicle_id_counter//4}")

# Show what happens step by step during cycle 1 green phase
print(f"\nStep-by-step during cycle 1 green (t={cycle_len}..{cycle_len+green_len-1}):")
print(f"{'t':>5} {'sig':>6} {'before_stop':>12} {'in_box':>7} {'exits_step':>11}")
for _, row in df_ex[(df_ex['t'] >= cycle_len) & (df_ex['t'] < cycle_len + green_len)].iterrows():
    print(f"{int(row['t']):>5} {row['sig0']:>6} {int(row['q_before']):>12} {int(row['in_box']):>7} {int(row['exits_this_step']):>11}")

print()
print("=" * 65)
print("D. Key capacity calculation")
print("=" * 65)
print(f"  Signal: green={green_len}s per {cycle_len}s cycle = {green_len/cycle_len*100:.1f}%")
print(f"  Box traverse distance (straight): 2 × {box_size//2}W = {2*box_size//2} cells ... wait: box_size={box_size}, exit={2*box_size}")
print(f"  Box traverse distance: {2*box_size} cells at max car speed {28} = {2*box_size/28:.1f}s per vehicle")
print(f"  Theoretical max throughput per leg per cycle: {green_len / (2*box_size/28):.1f} vehicles")
print(f"  Actual arrivals at 800 veh/hr per cycle: {800*cycle_len/3600:.1f} vehicles")
print(f"  Ratio (arrivals/capacity): {(800*cycle_len/3600) / (green_len / (2*box_size/28)):.2f}x")
