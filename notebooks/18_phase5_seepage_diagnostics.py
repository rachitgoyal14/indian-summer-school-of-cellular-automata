"""
Phase 5 Seepage — Diagnostics and Acceptance Criteria Verification

Covers:
  1. Verify seep advance distances match configured values exactly
  2. Two-panel space-time trajectory plot: seepage off vs on
  3. FIFO violation count and rate
  4. Cars/buses never seep — explicit assertion
  5. Summary report printed to stdout
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_seepage

# ─────────────────────────────────────────────────────────────────────────────
# Config and real-mode mix
# ─────────────────────────────────────────────────────────────────────────────
config = load_config("configs/intersection_default.yaml")

# Real Kanagaraj mode mix (from base.pdf / Phase 0 data analysis)
REAL_MODE_MIX = {
    'two_wheeler':   0.546,
    'car':           0.267,
    'three_wheeler': 0.151,
    'bus':           0.036,
}

RATE_VEH_PER_HOUR = 800
# 5+ signal cycles = 5 × 130s = 650s — run 8 cycles for comfortable margin
DURATION_S = 1040   # 8 × 130s

rng_off = np.random.default_rng(seed=42)
rng_on  = np.random.default_rng(seed=42)

road_length_cells = int(config['midblock_test']['road_length_m'] / config['grid']['cell_length_m'])
stop_line_cells   = road_length_cells - 100
cell_length_m     = config['grid']['cell_length_m']

print("=" * 70)
print("Phase 5 Seepage Diagnostics")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Run seepage-OFF baseline
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/5] Running seepage-OFF baseline (8 cycles, 800 veh/hr)...")
df_off = run_single_leg_with_seepage(
    config, RATE_VEH_PER_HOUR, DURATION_S, REAL_MODE_MIX, rng_off,
    seepage_eligible_modes_override=[],   # OFF
)
print(f"      Records: {len(df_off):,}  |  Vehicles: {df_off['vehicle_id'].nunique()}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Run seepage-ON
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2/5] Running seepage-ON (8 cycles, 800 veh/hr)...")
df_on = run_single_leg_with_seepage(
    config, RATE_VEH_PER_HOUR, DURATION_S, REAL_MODE_MIX, rng_on,
    seepage_eligible_modes_override=None,  # ON — uses config default
)
print(f"      Records: {len(df_on):,}  |  Vehicles: {df_on['vehicle_id'].nunique()}")

# Seepage action breakdown
action_counts = df_on['seepage_action'].value_counts(dropna=False)
print("\n  Seepage action breakdown (seepage-ON run):")
for action, count in action_counts.items():
    print(f"    {str(action):20s} : {count:6,}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Verify advance distances match configured values
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3/5] Verifying seepage advance distances match config...")

advance_map = config.get('seepage_advance_cells_per_step', {})
seeping_rows = df_on[df_on['seepage_action'].isin(
    ['seep_left', 'seep_right', 'seep_diagonal'])].copy()

if len(seeping_rows) == 0:
    print("  WARNING: No seepage moves found in the run!")
else:
    # Method 1: Check logged speed_cells_per_step == configured advance.
    # sim_loop restores speed = advance after each seep move (original_speeds restore),
    # so the logged speed for seeping rows SHOULD exactly equal the configured advance.
    print("  Method 1: logged speed_cells_per_step == configured advance (direct check):")
    all_correct = True
    for mode, expected_advance in advance_map.items():
        mode_seeps = seeping_rows[seeping_rows['mode'] == mode]
        if len(mode_seeps) == 0:
            print(f"    {mode:15s}: 0 seep events (OK if mode rare)")
            continue
        wrong = mode_seeps[mode_seeps['speed_cells_per_step'] != expected_advance]
        status = "✓" if len(wrong) == 0 else f"✗ MISMATCH ({len(wrong)} rows)"
        print(f"    {mode:15s}: expected speed={expected_advance}  "
              f"correct={len(mode_seeps)-len(wrong)}/{len(mode_seeps)} {status}")
        if len(wrong) > 0:
            all_correct = False
            print(f"      Wrong speeds: {wrong['speed_cells_per_step'].value_counts().to_dict()}")

    # Method 2: Position diff — correctly computed by joining against t-1 in the FULL df.
    # Build a lookup: (vehicle_id, time_s) → position_cells from the complete df.
    print("  Method 2: position diff (seep_pos_t - full_df_pos_{t-1}):")
    pos_lookup = df_on.set_index(['vehicle_id', 'time_s'])['position_cells']

    mismatches_m2 = 0
    total_m2 = 0
    for mode, expected_advance in advance_map.items():
        mode_seeps = seeping_rows[seeping_rows['mode'] == mode]
        correct_m2 = 0
        total_mode = 0
        for _, row in mode_seeps.iterrows():
            vid, t = int(row['vehicle_id']), int(row['time_s'])
            cur_pos = row['position_cells']
            try:
                prev_pos = pos_lookup.loc[(vid, t - 1)]
            except KeyError:
                continue  # vehicle first appeared at t, no t-1
            delta = cur_pos - prev_pos
            total_mode += 1
            if delta == expected_advance:
                correct_m2 += 1
        total_m2 += total_mode
        if total_mode > 0:
            wrong_m2 = total_mode - correct_m2
            status = "✓" if wrong_m2 == 0 else f"✗ {wrong_m2} mismatches"
            print(f"    {mode:15s}: correct={correct_m2}/{total_mode} {status}")

    if all_correct:
        print("  All logged speeds match configured advance values. ✓")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cars/buses never seep — explicit assertion
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4/5] Verifying cars/buses never perform seepage...")

car_seeps = df_on[(df_on['mode'] == 'car') & 
                   (df_on['seepage_action'].isin(['seep_left', 'seep_right', 'seep_diagonal']))]
bus_seeps = df_on[(df_on['mode'] == 'bus') & 
                   (df_on['seepage_action'].isin(['seep_left', 'seep_right', 'seep_diagonal']))]

print(f"  Car seep events  : {len(car_seeps)}  (expected 0)")
print(f"  Bus seep events  : {len(bus_seeps)}  (expected 0)")

car_bus_ok = len(car_seeps) == 0 and len(bus_seeps) == 0
print(f"  Cars/buses never seep: {'✓ PASS' if car_bus_ok else '✗ FAIL'}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. FIFO violation analysis
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5/5] Computing FIFO violation count and rate (seepage-ON run)...")

# Method: FIFO is violated when a vehicle that ARRIVED LATER overtakes one that arrived EARLIER.
# We define "first arrival time" as the first timestep each vehicle appears in the data.
# We detect a violation at timestep t if vehicle A (arrived later) has position > vehicle B (arrived earlier)
# AND both are on the same lateral column (or close enough to meaningfully compare rank).
#
# For a single-leg simulation, we measure FIFO by tracking each vehicle's first-seen time
# and checking if relative ordering (by position_cells) ever changes relative to arrival order.
#
# Practical approach: for each timestep, sort vehicles by position (high=near front).
# FIFO violation = a vehicle that arrived LATER is currently AHEAD of one that arrived earlier,
# AND both are in the IZOI / queued region (position > stop_line - max_izoi_dist).

# Build vehicle arrival order (first timestep seen)
arrival_order = df_on.groupby('vehicle_id')['time_s'].min().rename('first_seen')
df_on_aug = df_on.join(arrival_order, on='vehicle_id')

max_izoi_m = max(config['izoi_distance_m'].values())
max_izoi_cells = int(max_izoi_m / cell_length_m)
izoi_start = stop_line_cells - max_izoi_cells

fifo_violations = 0
fifo_violation_events = []

for t, grp in df_on_aug[df_on_aug['position_cells'] >= izoi_start].groupby('time_s'):
    if len(grp) < 2:
        continue
    # Sort by position descending (front-first)
    grp_sorted = grp.sort_values('position_cells', ascending=False)
    positions = grp_sorted['position_cells'].values
    arrivals  = grp_sorted['first_seen'].values
    vids      = grp_sorted['vehicle_id'].values
    
    # Check: for each pair (i, j) where i is ahead (higher pos), if arrival[i] > arrival[j],
    # that's a FIFO violation (vehicle j arrived first but is now behind vehicle i).
    # O(n^2) — only run on IZOI vehicles which should be manageable.
    n = len(grp_sorted)
    for i in range(n):
        for j in range(i + 1, n):
            # i is ahead of j (positions[i] >= positions[j] since sorted descending)
            if arrivals[i] > arrivals[j]:
                # Vehicle i arrived LATER but is AHEAD of vehicle j
                fifo_violations += 1
                if len(fifo_violation_events) < 10:
                    fifo_violation_events.append({
                        't': t, 'ahead_vid': vids[i], 'behind_vid': vids[j],
                        'ahead_arrival': arrivals[i], 'behind_arrival': arrivals[j],
                        'ahead_pos': positions[i], 'behind_pos': positions[j],
                    })

total_timestep_pairs = sum(
    len(grp) * (len(grp) - 1) // 2
    for _, grp in df_on_aug[df_on_aug['position_cells'] >= izoi_start].groupby('time_s')
    if len(grp) >= 2
)

fifo_rate = fifo_violations / total_timestep_pairs if total_timestep_pairs > 0 else 0.0
print(f"  Total timestep×pair checks in IZOI : {total_timestep_pairs:,}")
print(f"  FIFO violations (pair-instants)    : {fifo_violations:,}")
print(f"  FIFO violation rate                : {fifo_rate:.4%}")
print(f"  Note: FIFO violations include overtaking due to LATERAL lane changes AND seepage.")
print(f"  In heterogeneous multi-lane traffic, some FIFO 'violations' are expected — ")
print(f"  what matters is whether the RATE is elevated in seepage-ON vs seepage-OFF.")

# Compute seepage-OFF FIFO rate for comparison
arrival_order_off = df_off.groupby('vehicle_id')['time_s'].min().rename('first_seen')
df_off_aug = df_off.join(arrival_order_off, on='vehicle_id')

fifo_violations_off = 0
total_timestep_pairs_off = 0

for t, grp in df_off_aug[df_off_aug['position_cells'] >= izoi_start].groupby('time_s'):
    if len(grp) < 2:
        continue
    grp_sorted = grp.sort_values('position_cells', ascending=False)
    arrivals  = grp_sorted['first_seen'].values
    n = len(grp_sorted)
    total_timestep_pairs_off += n * (n - 1) // 2
    for i in range(n):
        for j in range(i + 1, n):
            if arrivals[i] > arrivals[j]:
                fifo_violations_off += 1

fifo_rate_off = fifo_violations_off / total_timestep_pairs_off if total_timestep_pairs_off > 0 else 0.0
print(f"\n  Seepage-OFF FIFO rate              : {fifo_rate_off:.4%}")
print(f"  Seepage-ON  FIFO rate              : {fifo_rate:.4%}")
print(f"  Delta (seepage adds)               : {fifo_rate - fifo_rate_off:+.4%}")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Collision check — seepage-ON run
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Collision check] Verifying zero cell-occupancy collisions (seepage-ON, 8 cycles)...")

mode_params = config['mode_params']
collision_count = 0
for t, grp in df_on.groupby('time_s'):
    occupancy = {}
    for _, row in grp.iterrows():
        vid = int(row['vehicle_id'])
        mode = row['mode']
        length = mode_params[mode]['length_cells']
        width  = mode_params[mode]['width_cells']
        front  = int(row['position_cells'])
        lat    = int(row['lateral_position_cells'])
        for x in range(front - length + 1, front + 1):
            for y in range(lat, lat + width):
                cell = (x, y)
                if cell in occupancy:
                    collision_count += 1
                    if collision_count <= 5:
                        print(f"  COLLISION at t={t}: v{occupancy[cell]} & v{vid} at {cell}")
                else:
                    occupancy[cell] = vid

print(f"  Total collisions detected: {collision_count}  ({'✓ PASS' if collision_count == 0 else '✗ FAIL'})")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Two-panel space-time trajectory plot
# ─────────────────────────────────────────────────────────────────────────────
print("\n[Plot] Generating two-panel space-time trajectory figure...")

# Filter to only vehicles that spent time in the IZOI zone for readability
fig, (ax_off, ax_on) = plt.subplots(1, 2, figsize=(16, 8), sharey=True)
fig.suptitle(
    "Phase 5 — Space-Time Trajectories: Seepage Off vs On\n"
    f"(Real mode mix: 54.6% two-wheeler, 26.7% car, 15.1% three-wheeler, 3.6% bus | "
    f"800 veh/hr, 8 signal cycles)",
    fontsize=11, fontweight='bold'
)

MODE_COLORS = {
    'two_wheeler':   '#1f77b4',
    'car':           '#ff7f0e',
    'three_wheeler': '#2ca02c',
    'bus':           '#d62728',
}

def draw_trajectories(ax, df, title, stop_line_cells, izoi_start, mode_colors):
    """Draw space-time plot for vehicles in the IZOI region."""
    # Convert cells to meters for y-axis
    cell_len = 0.5  # m per cell
    
    # Signal shading (red periods)
    cycle_length = 130
    green_s = 30
    red_s   = 100
    max_t = df['time_s'].max()
    t = 0
    while t <= max_t:
        red_start = t + green_s
        red_end   = min(red_start + red_s, max_t)
        ax.axhspan(red_start, red_end, color='#ffcccc', alpha=0.5, linewidth=0)
        t += cycle_length
    
    # Stop line
    stop_m = stop_line_cells * cell_len
    ax.axvline(stop_m, color='black', linestyle='--', linewidth=1.5, label='Stop line')
    
    # Seepage action column
    has_seepage = 'seepage_action' in df.columns
    
    # Draw one trajectory per vehicle, colored by mode
    for vid, vdf in df.groupby('vehicle_id'):
        mode = vdf['mode'].iloc[0]
        color = mode_colors.get(mode, 'gray')
        vdf_sorted = vdf.sort_values('time_s')
        pos_m = vdf_sorted['position_cells'] * cell_len
        times  = vdf_sorted['time_s']
        ax.plot(pos_m, times, color=color, linewidth=0.6, alpha=0.7)
        
        # Highlight seepage events with markers
        if has_seepage:
            seep_rows = vdf_sorted[vdf_sorted['seepage_action'].isin(['seep_left', 'seep_right', 'seep_diagonal'])]
            if len(seep_rows) > 0:
                ax.scatter(seep_rows['position_cells'] * cell_len, seep_rows['time_s'],
                           s=6, c='gold', zorder=5, linewidths=0)
    
    # Annotate
    ax.set_xlabel("Position (m)", fontsize=10)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.invert_xaxis()  # position increases toward stop line → put stop line on right side
    ax.set_xlim(left=stop_m + 20, right=(izoi_start - 20) * cell_len)
    
    # Signal legend patch
    red_patch = mpatches.Patch(color='#ffcccc', alpha=0.5, label='Red signal')
    ax.legend(handles=[
        mpatches.Patch(color=mode_colors['two_wheeler'], label='Two-wheeler'),
        mpatches.Patch(color=mode_colors['car'],         label='Car'),
        mpatches.Patch(color=mode_colors['three_wheeler'], label='Three-wheeler'),
        mpatches.Patch(color=mode_colors['bus'],         label='Bus'),
        red_patch,
    ] + ([mpatches.Patch(color='gold', label='Seep event')] if has_seepage else []),
               fontsize=8, loc='upper left')

ax_off.set_ylabel("Time (s)", fontsize=10)

draw_trajectories(ax_off, df_off, "Seepage OFF", stop_line_cells, izoi_start, MODE_COLORS)
draw_trajectories(ax_on,  df_on,  "Seepage ON",  stop_line_cells, izoi_start, MODE_COLORS)

plt.tight_layout()
out_path = os.path.join(os.path.dirname(__file__), '..', 'figures', 'phase5_seepage_trajectories.png')
plt.savefig(out_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"  Saved: {os.path.abspath(out_path)}")

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("PHASE 5 ACCEPTANCE CRITERIA SUMMARY")
print("=" * 70)
print(f"  ✓ Zero collisions in 8-cycle seepage-heavy run: {collision_count == 0}")
print(f"  ✓ Cars never seep: {len(car_seeps) == 0}")
print(f"  ✓ Buses never seep: {len(bus_seeps) == 0}")
print(f"  FIFO violation rate (seepage-ON)  : {fifo_rate:.4%}")
print(f"  FIFO violation rate (seepage-OFF) : {fifo_rate_off:.4%}")
print(f"  FIFO delta (seepage contribution) : {fifo_rate - fifo_rate_off:+.4%}")
print(f"  Space-time figure saved: figures/phase5_seepage_trajectories.png")
print("=" * 70)
