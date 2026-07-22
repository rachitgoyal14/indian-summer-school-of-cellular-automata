"""
Prerequisite check for Phase 6:
Does the junction box allow multiple non-conflicting same-leg vehicles
simultaneously inside, or does it force single-occupancy serialization?

Expected (good): multiple vehicles from the same leg can be inside the box
simultaneously as long as decelerate_for_gap maintains their headway — the
same car-following gap as on the midblock.

Bug scenario: if the entry check mistakenly blocks vehicle N from entering
while vehicle N-1 is still inside, only one vehicle per leg is in the box
at any moment — throughput ceiling ~583 veh/hr instead of ~1800+ veh/hr
governed by discharge headway.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from src.core.config import load_config
from src.intersection.intersection import Intersection

CONFIG_PATH = "configs/intersection_default.yaml"
config = load_config(CONFIG_PATH)

rng = np.random.default_rng(seed=42)

# Run 5 full signal cycles (650s) at a moderate rate
RATE = 1200  # veh/hr per leg — saturated but below extreme
DURATION = 650  # 5 × 130s cycles

intersection = Intersection(config, RATE, DURATION, {
    'two_wheeler': 0.546,
    'car': 0.267,
    'three_wheeler': 0.151,
    'bus': 0.036,
}, rng)

# Track box occupancy counts per leg per timestep
box_counts = {leg_id: [] for leg_id in range(4)}
box_count_all = []

for t in range(DURATION):
    _ = intersection.step(t)
    for leg in intersection.legs:
        W = intersection.box_size // 2
        in_box = [v for v in leg.vehicles
                  if v.position_cells - leg.stop_line_position_cells >= 0]
        box_counts[leg.leg_id].append(len(in_box))
    total = sum(len([v for v in leg.vehicles
                     if v.position_cells - leg.stop_line_position_cells >= 0])
                for leg in intersection.legs)
    box_count_all.append(total)

print("=" * 60)
print("BOX SERIALIZATION CHECK RESULTS")
print("=" * 60)
print(f"\nRate: {RATE} veh/hr/leg | Duration: {DURATION}s")
print(f"Natural exits: {intersection.natural_exits_count}")
print(f"Forced exits:  {intersection.forced_crossings_count}")

for leg_id in range(4):
    counts = box_counts[leg_id]
    arr = np.array(counts)
    print(f"\nLeg {leg_id}:")
    print(f"  Max simultaneous in box: {arr.max()}")
    print(f"  Mean simultaneous:       {arr.mean():.3f}")
    print(f"  Timesteps with >1 in box:{(arr > 1).sum()}  ({(arr > 1).mean()*100:.1f}%)")
    print(f"  Timesteps with >2 in box:{(arr > 2).sum()}  ({(arr > 2).mean()*100:.1f}%)")

all_arr = np.array(box_count_all)
print(f"\nAll legs combined:")
print(f"  Max simultaneous in box: {all_arr.max()}")
print(f"  Mean simultaneous:       {all_arr.mean():.3f}")
print(f"  Timesteps with >4 in box:{(all_arr > 4).sum()} ({(all_arr > 4).mean()*100:.1f}%)")

print("\n=== Verdict ===")
max_single = max(np.array(box_counts[i]).max() for i in range(4))
if max_single > 1:
    print(f"✓ NOT SERIALIZED: up to {max_single} vehicles from the same leg")
    print("  are simultaneously inside the box — car-following spacing honored.")
    print("  This is CORRECT: throughput governed by headway, not box-traverse time.")
else:
    print("✗ SERIALIZED BUG DETECTED: only 1 vehicle per leg ever in box at a time!")
    print("  This artificially caps throughput to ~583 veh/hr. Fix required.")
