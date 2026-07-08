"""
Micro-investigation: How long do vehicles actually spend in the junction box?
And are there cross-phase vehicles lingering when Phase A green starts?
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import yaml

with open("configs/intersection_default.yaml") as f:
    config = yaml.safe_load(f)

from src.intersection.intersection import Intersection

RATE = 800
cycle_len = config['signal']['cycle_length_s']  # 130
green_len = config['signal']['green_s']          # 30
DURATION = 390  # 3 cycles

rng = np.random.default_rng(42)
inter = Intersection(config, RATE, DURATION, {"car": 1.0}, rng)

# Track:
# - When each vehicle enters the box (pos_past >= 0)
# - When each vehicle exits
# - Which leg it's on and its signal phase
box_entry = {}     # vid -> (t, leg_id)
box_exit = {}      # vid -> (t, leg_id, dwell_s)
in_box_per_step = []  # (t, leg_id, count_in_box)

# Also track: at each Phase A green start, what's in the box?
phase_a_green_starts = [t for t in range(DURATION) if t % cycle_len == 0]
phase_b_green_starts = [t for t in range(DURATION) if t % cycle_len == cycle_len // 2]  # offset=65

for t in range(DURATION):
    # Snapshot before step
    for leg in inter.legs:
        stop_l = leg.stop_line_position_cells
        for v in leg.vehicles:
            pos_past = v.position_cells - stop_l
            if pos_past >= 0 and v.id not in box_entry:
                box_entry[v.id] = (t, leg.leg_id)
    
    # Check: right before Phase A green, what legs have vehicles in box?
    if t in phase_a_green_starts:
        in_box_summary = {}
        for leg in inter.legs:
            stop_l = leg.stop_line_position_cells
            in_box = [(v.id, v.position_cells - stop_l) for v in leg.vehicles if v.position_cells >= stop_l]
            in_box_summary[leg.leg_id] = in_box
        if any(len(v) > 0 for v in in_box_summary.values()):
            print(f"\nAt Phase A green start (t={t}, t%{cycle_len}=0):")
            for lid, vehicles in in_box_summary.items():
                sig = inter.legs[lid].signal.state_at(t)
                if vehicles:
                    print(f"  Leg {lid} (signal={sig}): {len(vehicles)} in box — {vehicles[:3]}...")
    
    if t in phase_b_green_starts:
        in_box_summary = {}
        for leg in inter.legs:
            stop_l = leg.stop_line_position_cells
            in_box = [(v.id, v.position_cells - stop_l) for v in leg.vehicles if v.position_cells >= stop_l]
            in_box_summary[leg.leg_id] = in_box
        if any(len(v) > 0 for v in in_box_summary.values()):
            print(f"\nAt Phase B green start (t={t}, t%{cycle_len}=65):")
            for lid, vehicles in in_box_summary.items():
                sig = inter.legs[lid].signal.state_at(t)
                if vehicles:
                    print(f"  Leg {lid} (signal={sig}): {len(vehicles)} in box — {vehicles[:3]}...")
    
    # Step
    inter.step(t)
    
    # Snapshot after step — find exits
    all_ids_after = set()
    for leg in inter.legs:
        stop_l = leg.stop_line_position_cells
        for v in leg.vehicles:
            all_ids_after.add(v.id)
    
    for vid, (entry_t, entry_leg) in list(box_entry.items()):
        if vid not in all_ids_after and vid not in box_exit:
            box_exit[vid] = (t, entry_leg, t - entry_t)

print(f"\n{'=' * 60}")
print(f"Box dwell time distribution (n={len(box_exit)} vehicles exited):")
if box_exit:
    dwell_times = [dw for _, _, dw in box_exit.values()]
    print(f"  Min: {min(dwell_times)}s, Max: {max(dwell_times)}s, Mean: {sum(dwell_times)/len(dwell_times):.1f}s")
    print(f"  Vehicles spending > 10s in box: {sum(1 for d in dwell_times if d > 10)}")
    print(f"  Vehicles spending > 30s in box: {sum(1 for d in dwell_times if d > 30)}")
    print(f"  Vehicles spending > green_len={green_len}s: {sum(1 for d in dwell_times if d > green_len)}")
    # Histogram
    from collections import Counter
    hist = Counter(min(d, 10) for d in dwell_times)
    print(f"\n  Dwell ≤10s histogram:")
    for k in sorted(hist):
        label = f"  {k}s" if k < 10 else " >9s"
        print(f"    {label}: {'#'*hist[k]} ({hist[k]})")

print(f"\n{'=' * 60}")
print(f"Per-leg exit counts:")
for lid in range(4):
    phase = "A" if lid in [0, 2] else "B"
    exits = sum(1 for _, el, _ in box_exit.values() if el == lid)
    print(f"  Leg {lid} (Phase {phase}): {exits} natural exits")
print(f"  Total forced: {inter.forced_crossings_count}")

print(f"\n{'=' * 60}")
print(f"Vehicles still in box at t={DURATION-1}:")
for leg in inter.legs:
    stop_l = leg.stop_line_position_cells
    in_box = [(v.id, v.position_cells - stop_l, inter.junction_entry_t.get(v.id, -1)) for v in leg.vehicles if v.position_cells >= stop_l]
    if in_box:
        print(f"  Leg {leg.leg_id}: {len(in_box)} — {in_box[:5]}")

# Key check: during cycle 2 green (t=260..289), what's blocking?
print(f"\n{'=' * 60}")
print(f"Snapshot at t=258 (2s before Phase A cycle 2 green):")
# We need to re-run because we already ran the sim... let's just note what was printed
print("(see Phase A green start snapshots above)")
