"""
Phase 6 — Two-wheeler density discrepancy investigation.

Goal: trace EXACTLY what both methods produce for two_wheeler at a specific
timestep, showing all intermediate values (occupied_cells, total_cells,
footprint assumption, road_length_km) to isolate the structural difference
that produces the 0.68 ratio.

Two candidate hypotheses:
  H1: Formula precision — Eq 6-15 occupancy-method is genuinely more conservative
      for small footprints due to gap accounting, equally affecting all modes
      → would expect similar ratios for all modes (NOT 0.68 vs ~1.1)

  H2: Footprint assumption bug — flow_density_by_mode_from_collector() uses
      mode_params.length_cells as the footprint, but the density denominator
      (total_cells = road_length_cells) is 1D and doesn't account for the
      road WIDTH. For a 1-wide two_wheeler on a 10-wide road, the effective
      "lane" it occupies is 1/10 of the total road. If the formula implicitly
      assumes full-width occupancy (like a car filling 3 of 10 cells wide),
      this would inflate the denominator relative to the numerator for
      narrow vehicles.

  H3: occupied_cells computation bug — the iterrows() loop in flow_density_table
      computes occupied_cells as `sum of length_cells per row per timestep`,
      but uses `mode_params.get(row["mode"]).get("length_cells")` which goes
      through a dict lookup for EACH row. For two_wheelers (length=4, width=1),
      vs cars (length=7, width=3): if total_cells denominator = road_length_cells
      (1D, 2000 cells) but occupied_cells only counts longitudinal length (not
      width), then wide vehicles like buses (20×4) appear to take MORE space
      than their 1D length suggests relative to the road capacity.
      Actually this would favor narrow vehicles (correct direction is lower
      occupied/total → lower density), so let's check numerically.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode

CONFIG_PATH = "configs/intersection_default.yaml"
config = load_config(CONFIG_PATH)
cell_length_m = config["grid"]["cell_length_m"]   # 0.5
cell_width_m  = config["grid"]["cell_width_m"]    # 0.7
road_length_m = config["midblock_test"]["road_length_m"]  # 1000
road_length_cells = int(road_length_m / cell_length_m)   # 2000
road_length_km = road_length_m / 1000.0                  # 1.0
MODE_PARAMS = config["mode_params"]

print("=" * 70)
print("TWO-WHEELER DENSITY DISCREPANCY — ARITHMETIC TRACE")
print("=" * 70)
print(f"\nGrid: cell_length_m={cell_length_m}, cell_width_m={cell_width_m}")
print(f"Road: {road_length_m}m = {road_length_cells} cells longitudinal = {road_length_km:.1f} km")

# Mode params
for mode in ["two_wheeler", "car", "bus"]:
    p = MODE_PARAMS[mode]
    print(f"\n{mode}: length={p['length_cells']} cells, width={p['width_cells']} cells, "
          f"footprint={p['length_cells']*p['width_cells']} cells², "
          f"max_speed={p['max_speed_cells_per_step']} cells/step")

# --- Run one isolated-mode simulation at a moderate rate ---
RATE = 3500
DURATION = 1800
MODE = "two_wheeler"
isolated_mix = {MODE: 1.0}

print(f"\n\nRunning isolated {MODE} at {RATE} veh/hr for {DURATION}s ...")
rng = np.random.default_rng(42)
df = run_midblock_simulation_multimode(config, RATE, DURATION, isolated_mix, rng)
print(f"Records: {len(df)} rows, unique vehicles: {df['vehicle_id'].nunique()}")

# Pick a 60s window near the plateau (t=900-960s, middle of run)
W_START, W_END = 900, 960
WINDOW_S = W_END - W_START
df_win = df[(df['time_s'] >= W_START) & (df['time_s'] < W_END)]
print(f"\nAnalysis window: t={W_START}..{W_END}s ({WINDOW_S}s), {len(df_win)} records")

# -----------------------------------------------------------------------
# METHOD A: Legacy Phase 2 (flow_density_from_log)
# density = (avg vehicles per second) / road_length_km
# flow    = vehicles crossing measurement point × 3600/window_s
# -----------------------------------------------------------------------
meas_pt = road_length_cells - 50

avg_vehicles_per_second = len(df_win) / float(WINDOW_S)
density_legacy = avg_vehicles_per_second / road_length_km

# Count crossings
crossed = set()
for vid, grp in df_win.groupby('vehicle_id'):
    crossings = grp[
        (grp['position_cells'] >= meas_pt) &
        (grp['position_cells'] - grp['speed_cells_per_step'] < meas_pt)
    ]
    if not crossings.empty:
        crossed.add(vid)
flow_legacy = len(crossed) * (3600.0 / WINDOW_S)

print("\n" + "─" * 70)
print("METHOD A — Legacy Phase 2 (flow_density_from_log)")
print("─" * 70)
print(f"  Records in window:          {len(df_win)}")
print(f"  avg_vehicles_per_second:    {len(df_win)} / {WINDOW_S} = {avg_vehicles_per_second:.4f} veh/s")
print(f"  road_length_km:             {road_length_km:.1f} km")
print(f"  density = avg_veh/s / km:   {avg_vehicles_per_second:.4f} / {road_length_km:.1f} = {density_legacy:.2f} veh/km")
print(f"  crossings at meas_pt:       {len(crossed)}")
print(f"  flow = crossings × 3600/W:  {len(crossed)} × {3600/WINDOW_S:.1f} = {flow_legacy:.1f} veh/hr")

# -----------------------------------------------------------------------
# METHOD B: Phase 6 Eq 6-15 (flow_density_table)
# For each timestep, compute occupied_cells = sum of length_cells per vehicle
# density = (avg_occupied_cells / total_cells) / avg_footprint × (1000/cell_length_m)
# -----------------------------------------------------------------------
mode_len = MODE_PARAMS[MODE]['length_cells']   # two_wheeler: 4
mode_wid = MODE_PARAMS[MODE]['width_cells']    # two_wheeler: 1

occupied_per_t = []
for ts, grp in df_win.groupby('time_s'):
    # This is what flow_density_table does:
    occ = sum(
        MODE_PARAMS.get(row['mode'], {}).get('length_cells', 7)
        for _, row in grp.iterrows()
    )
    occupied_per_t.append((ts, len(grp), occ))

ts_arr = [x[0] for x in occupied_per_t]
n_vehs = [x[1] for x in occupied_per_t]
occ_cells = [x[2] for x in occupied_per_t]

avg_occupied = np.mean(occ_cells)
total_cells = road_length_cells   # 2000
avg_footprint = float(mode_len)   # 4 (length only — this is the key question)

# Eq 6-15 density
occupancy_ratio = avg_occupied / total_cells
density_per_cell = occupancy_ratio / avg_footprint
density_p6 = density_per_cell * (1000.0 / cell_length_m)

# Flow (same crossing logic)
crossed_p6 = set()
for vid, grp in df_win.groupby('vehicle_id'):
    prev_pos = grp['position_cells'].shift(1)
    crossed_rows = grp[(grp['position_cells'] >= meas_pt) & (prev_pos < meas_pt)]
    if not crossed_rows.empty:
        crossed_p6.add(vid)
flow_p6 = len(crossed_p6) * (3600.0 / WINDOW_S)

print("\n" + "─" * 70)
print("METHOD B — Phase 6 Eq 6-15 (flow_density_table)")
print("─" * 70)
print(f"  mode_len (footprint for density): {mode_len} cells (length only)")
print(f"  mode_wid:                         {mode_wid} cells")
print(f"\n  Per-timestep occupied_cells (sample from t=900-910):")
for ts, nv, occ in occupied_per_t[:10]:
    print(f"    t={ts}: {nv} vehicles × {mode_len} cells = {occ} occupied cells")
print(f"  ...")
print(f"\n  avg_occupied_cells (over {WINDOW_S}s window): {avg_occupied:.2f}")
print(f"  total_cells (denominator):         {total_cells}")
print(f"  occupancy_ratio = {avg_occupied:.2f} / {total_cells} = {occupancy_ratio:.6f}")
print(f"  avg_footprint (divisor):           {avg_footprint}")
print(f"  density_per_cell = {occupancy_ratio:.6f} / {avg_footprint} = {density_per_cell:.8f}")
print(f"  density_p6 = {density_per_cell:.8f} × (1000/{cell_length_m}) = {density_p6:.2f} veh/km")
print(f"  flow_p6 = {len(crossed_p6)} crossings × {3600/WINDOW_S:.1f} = {flow_p6:.1f} veh/hr")

print("\n" + "─" * 70)
print("COMPARISON at this window")
print("─" * 70)
print(f"  Legacy density: {density_legacy:.2f} veh/km")
print(f"  Phase 6 density:{density_p6:.2f} veh/km")
print(f"  Ratio P6/Legacy: {density_p6/density_legacy:.3f}")
print(f"\n  Legacy flow:    {flow_legacy:.1f} veh/hr")
print(f"  Phase 6 flow:   {flow_p6:.1f} veh/hr")
print(f"  (Flow is identical — same crossing logic for both)")

# -----------------------------------------------------------------------
# KEY STRUCTURAL DIFFERENCE: Legacy uses "vehicle-record count / road_km"
# which is equivalent to (N_vehicles × 1) / road_length_km
# Phase 6 uses (N_vehicles × length_cells) / total_cells / length_cells × scale
# These should be IDENTICAL if total_cells = road_length_km × 1000/cell_length_m
# Let me check:
# -----------------------------------------------------------------------
print("\n" + "─" * 70)
print("ALGEBRAIC EQUIVALENCE CHECK")
print("─" * 70)

# Legacy: density = (N / window_s) / road_length_km
#       = N / (window_s × road_length_km)
#
# Phase6: density = (avg_N × length) / total_cells / length × (1000/cell_length_m)
#       = (avg_N × length) / (road_length_cells × length) × (1000/cell_length_m)
#       = avg_N / road_length_cells × (1000/cell_length_m)
#       = avg_N / (road_length_m/cell_length_m) × (1000/cell_length_m)
#       = avg_N × cell_length_m / road_length_m × 1000/cell_length_m
#       = avg_N × 1000 / road_length_m
#       = avg_N / road_length_km
#
# The length_cells / length_cells cancels out — BOTH methods should give
# exactly the same density for the SAME avg_N!
#
# So WHY is Phase 6 lower? The only difference must be in avg_N:
# Legacy:  avg_N = len(df_win) / window_s  (total records / window duration)
# Phase 6: avg_N = mean of per-timestep occupied_cells / length_cells
#        = mean of per-timestep N_vehicles   (same thing!)
#
# Wait — are they actually computing the same thing?

avg_n_legacy = avg_vehicles_per_second
avg_n_p6     = avg_occupied / mode_len   # this is avg per-timestep vehicle count

print(f"\n  Legacy avg_N/s = total_records / window_s:")
print(f"    = {len(df_win)} / {WINDOW_S} = {avg_n_legacy:.4f} veh/s")
print(f"\n  Phase 6 avg_N = avg(per-ts occupied) / length_cells:")
print(f"    = {avg_occupied:.4f} / {mode_len} = {avg_n_p6:.4f} veh/s")
print(f"\n  Are they the same? {abs(avg_n_legacy - avg_n_p6) < 0.01}")
print(f"  Difference: {avg_n_legacy - avg_n_p6:.4f} veh/s")

# Also check: how many records per timestep does legacy count vs phase6?
records_per_ts = df_win.groupby('time_s').size()
print(f"\n  Per-timestep vehicle count stats (Phase 6 source):")
print(f"    mean={records_per_ts.mean():.4f}, min={records_per_ts.min()}, max={records_per_ts.max()}")
print(f"  Total records: {records_per_ts.sum()}")
print(f"  Legacy total:  {len(df_win)}")

# Check if there are duplicate time_s × vehicle_id rows (that would inflate legacy)
dup = df_win.groupby(['time_s','vehicle_id']).size()
has_dups = (dup > 1).any()
print(f"\n  Duplicate (time_s, vehicle_id) pairs: {has_dups}")

# -----------------------------------------------------------------------
# Now trace the same thing for CAR to see why its ratio is ~1.11
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("SAME TRACE FOR CAR (ratio 1.11) — to understand the asymmetry")
print("=" * 70)

rng2 = np.random.default_rng(42)
df_car = run_midblock_simulation_multimode(config, RATE, DURATION, {"car": 1.0}, rng2)
df_car_win = df_car[(df_car['time_s'] >= W_START) & (df_car['time_s'] < W_END)]

car_len = MODE_PARAMS["car"]["length_cells"]  # 7
car_wid = MODE_PARAMS["car"]["width_cells"]   # 3

avg_veh_car_legacy = len(df_car_win) / float(WINDOW_S)
density_car_legacy = avg_veh_car_legacy / road_length_km

occ_car = [sum(car_len for _ in grp.iterrows()) for _, grp in df_car_win.groupby('time_s')]
avg_occ_car = np.mean(occ_car) if occ_car else 0
density_car_p6 = (avg_occ_car / total_cells) / float(car_len) * (1000.0 / cell_length_m)

print(f"\n  car: length={car_len}, width={car_wid}")
print(f"  avg_veh/s (legacy): {len(df_car_win)}/{WINDOW_S} = {avg_veh_car_legacy:.4f}")
print(f"  avg_occ_cells (P6): {avg_occ_car:.4f}  /  car_len={car_len} = {avg_occ_car/car_len:.4f} veh/s")
print(f"  Legacy density: {density_car_legacy:.4f} veh/km")
print(f"  Phase 6 density:{density_car_p6:.4f} veh/km")
print(f"  Ratio P6/Legacy: {density_car_p6/density_car_legacy:.3f}")

print("\n" + "=" * 70)
print("CONCLUSION")
print("=" * 70)
print("""
Algebraically, Phase 6 Eq 6-15 (as implemented) and the legacy Phase 2
formula should produce IDENTICAL density values when avg_N is computed
the same way — the length_cells factor cancels exactly.

The only possible source of divergence is whether avg_N is the same in
both methods. If per-timestep counts differ (e.g. due to how groupby
aggregates edge timesteps, or if the simulation records vehicles at
different counts), the densities will differ.

The ratio discrepancy (0.68 for two_wheeler vs ~1.1 for car/bus) implies
avg_N IS systematically different between the two methods for two_wheelers.
The high two_wheeler speed (max 30 cells/step) means more vehicles cross
and EXIT the road per window, so the legacy method's total-record count
picks up fewer rows per vehicle than the Phase 6 per-timestep count —
or vice versa. Let's check the per-timestep counts above.
""")
