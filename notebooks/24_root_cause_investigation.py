"""
Root-cause investigation of the 0.68 two_wheeler ratio.

The arithmetic trace proved: for the SAME simulation run, both methods
produce identical density (ratio 1.000). So the 0.68 ratio in the
isolated-mode comparison (script 22) must come from comparing DIFFERENT
things.

Script 22 did:
  - LEGACY method: called flow_density_by_mode(df, ...) — but df comes
    from run_midblock_simulation_multimode which uses the COLLECTOR path
    (use_collector=True). The legacy method is then called on collector_df
    which has the Phase 6 schema (14 columns, including "mode" etc).
  - Phase 6 method: called flow_density_by_mode_from_collector(df, ...)

  BUT: the legacy function flow_density_by_mode() uses the OLD crossing
  detection logic:
      group["position_cells"] - group["speed_cells_per_step"] < meas_pt
  which computes "previous position = current_pos - current_speed".

  The Phase 6 function uses .shift(1) to get the ACTUAL previous position
  from the DataFrame.

  For two_wheelers with max_speed=30 (15 m/s at 0.5 m/cell), a vehicle
  can travel 30 cells in one step. If it's at position 1990 with speed 30:
    Legacy:  prev_pos_approx = 1990 - 30 = 1960 → crosses meas_pt=1950  ✓
    Phase 6: prev_pos_actual = last row position → correct

  But what if the vehicle SPAWNS or ENTERS already past the measurement
  point? Then:
    Legacy:  prev_pos_approx = 1990 - 30 = 1960 → may or may not cross 1950
    Phase 6: prev_pos_actual = NaN (first row) → no crossing recorded

  This would make Phase 6 flow LOWER than Legacy for fast vehicles.
  At high rates, many two_wheelers enter and exit within one window,
  appearing as "first-timestep already past meas_pt" entries.

Let's verify by checking script 22's FLOW comparison, not density.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import (
    flow_density_by_mode_from_collector,
    flow_density_by_mode,
)

CONFIG_PATH = "configs/intersection_default.yaml"
config = load_config(CONFIG_PATH)
cell_length_m = config["grid"]["cell_length_m"]
road_length_m = config["midblock_test"]["road_length_m"]
road_length_cells = int(road_length_m / cell_length_m)
MODE_PARAMS = config["mode_params"]

road_geometry = {"road_length_cells": road_length_cells, "cell_length_m": cell_length_m}
meas_pt = road_length_cells - 50   # 1950

print("=" * 70)
print("ROOT-CAUSE: WHY DID SCRIPT 22 SHOW 0.68 FOR TWO_WHEELERS?")
print("=" * 70)

# --- Re-run the SAME set of rates as script 22 ---
RATES = [200, 500, 800, 1200, 1800, 2500, 3500, 5000, 8000, 12000]
DURATION = 1800
WINDOW_S = 60

print("\nSweeping rates for two_wheeler (isolated)...")
tw_data_p6 = {"flow": []}
tw_data_leg = {"flow": []}

for rate in RATES:
    rng = np.random.default_rng(42)
    df = run_midblock_simulation_multimode(config, rate, DURATION, {"two_wheeler": 1.0}, rng)

    # Phase 6 method
    fd_p6 = flow_density_by_mode_from_collector(df, road_geometry, window_s=WINDOW_S,
                                                mode_params=MODE_PARAMS)
    p6_flows = fd_p6.get("two_wheeler", pd.DataFrame())
    p6_peak = p6_flows["flow_veh_per_hr"].max() if not p6_flows.empty else 0.0

    # Legacy method — ALSO called on the same collector df
    fd_leg = flow_density_by_mode(df, road_length_cells, cell_length_m, WINDOW_S)
    leg_flows = fd_leg.get("two_wheeler", pd.DataFrame())
    leg_peak = leg_flows["flow_veh_per_hr"].max() if not leg_flows.empty else 0.0

    tw_data_p6["flow"].append(p6_peak)
    tw_data_leg["flow"].append(leg_peak)
    print(f"  Rate {rate:>6}: P6 peak={p6_peak:.0f}  Legacy peak={leg_peak:.0f}  ratio={p6_peak/leg_peak:.3f}" if leg_peak>0 else f"  Rate {rate:>6}: P6={p6_peak:.0f} Legacy={leg_peak:.0f}")

print(f"\nP6 max flow:     {max(tw_data_p6['flow']):.0f} veh/hr")
print(f"Legacy max flow: {max(tw_data_leg['flow']):.0f} veh/hr")
overall_ratio = max(tw_data_p6['flow']) / max(tw_data_leg['flow']) if max(tw_data_leg['flow']) > 0 else 0
print(f"Peak ratio:      {overall_ratio:.3f}")

# --- Now compare Phase 6 flow method vs legacy flow method at ONE window ---
print("\n\n" + "─" * 70)
print("CROSSING DETECTION COMPARISON at rate=3500, window t=900-960")
print("─" * 70)

rng = np.random.default_rng(42)
df = run_midblock_simulation_multimode(config, 3500, 1800, {"two_wheeler": 1.0}, rng)
df_win = df[(df["time_s"] >= 900) & (df["time_s"] < 960)]

# Phase 6 method: uses shift(1) for previous position
crossed_p6 = set()
for vid, grp in df_win.groupby("vehicle_id"):
    prev_pos = grp["position_cells"].shift(1)
    crossed_rows = grp[(grp["position_cells"] >= meas_pt) & (prev_pos < meas_pt)]
    if not crossed_rows.empty:
        crossed_p6.add(vid)

# Legacy method: uses pos - speed as approx prev_pos
crossed_leg = set()
for vid, grp in df_win.groupby("vehicle_id"):
    crossed_rows = grp[
        (grp["position_cells"] >= meas_pt) &
        (grp["position_cells"] - grp["speed_cells_per_step"] < meas_pt)
    ]
    if not crossed_rows.empty:
        crossed_leg.add(vid)

print(f"  Phase 6 (shift-1) crossings:  {len(crossed_p6)}")
print(f"  Legacy (pos-speed) crossings: {len(crossed_leg)}")

# Find vehicles detected by legacy but NOT Phase 6
only_legacy = crossed_leg - crossed_p6
only_p6 = crossed_p6 - crossed_leg
print(f"\n  Only in legacy (false-positive?): {len(only_legacy)}")
print(f"  Only in Phase 6 (false-negative?): {len(only_p6)}")

# Inspect one vehicle that's in legacy only
if only_legacy:
    vid = next(iter(only_legacy))
    rows = df_win[df_win["vehicle_id"] == vid].sort_values("time_s")
    print(f"\n  Example vehicle {vid} (only legacy crosses):")
    print(rows[["time_s","position_cells","speed_cells_per_step"]].to_string(index=False))
    # check global records for this vehicle to see what happens around meas_pt
    all_rows = df[df["vehicle_id"]==vid].sort_values("time_s")
    near_meas = all_rows[(all_rows["position_cells"] >= meas_pt - 40) &
                         (all_rows["position_cells"] <= meas_pt + 40)]
    print(f"\n  All records near meas_pt={meas_pt} (global):")
    print(near_meas[["time_s","position_cells","speed_cells_per_step"]].to_string(index=False))

if only_p6:
    vid = next(iter(only_p6))
    rows = df_win[df_win["vehicle_id"] == vid].sort_values("time_s")
    print(f"\n  Example vehicle {vid} (only Phase 6 crosses):")
    print(rows[["time_s","position_cells","speed_cells_per_step"]].to_string(index=False))

# --- The actual source of the 0.68 ratio in script 22 ---
print("\n\n" + "=" * 70)
print("CHECKING WHAT SCRIPT 22 ACTUALLY MEASURED")
print("=" * 70)
print("""
Script 22 (22_phase6_ordering_investigation.py) called:
  flow_density_by_mode_from_collector(df, road_geometry, window_s=60, mode_params=MODE_PARAMS)
  for each isolated-mode run over RATES = [200,500,...,12000]

The Phase 6 reference = 13,860 veh/hr (two_wheeler)
The Phase 2 reference = 20,364 veh/hr (from a prior script)

BUT: Phase 2's 20,364 figure came from a DIFFERENT simulation run — 
likely with different random seed, different duration, or a DIFFERENT
midblock function (run_midblock_simulation — the SINGLE-LANE legacy function,
NOT run_midblock_simulation_multimode which uses multiple lateral lanes).

Let's check: what does the LEGACY function produce for two_wheelers
on the SAME runs that script 22 used?
""")

print("Re-running script 22's exact sweep for two_wheeler, comparing:")
print("  A) Phase 6 flow_density_by_mode_from_collector (script 22 used)")
print("  B) Legacy flow_density_by_mode (on same df)")
print()

p6_peaks = []
leg_peaks = []
for rate in RATES:
    rng = np.random.default_rng(42)
    df = run_midblock_simulation_multimode(config, rate, DURATION, {"two_wheeler": 1.0}, rng)
    fd_p6 = flow_density_by_mode_from_collector(df, road_geometry, window_s=WINDOW_S, mode_params=MODE_PARAMS)
    fd_leg = flow_density_by_mode(df, road_length_cells, cell_length_m, WINDOW_S)
    p6 = fd_p6.get("two_wheeler", pd.DataFrame())
    leg = fd_leg.get("two_wheeler", pd.DataFrame())
    p6_peak = p6["flow_veh_per_hr"].max() if not p6.empty else 0.0
    leg_peak = leg["flow_veh_per_hr"].max() if not leg.empty else 0.0
    p6_peaks.append(p6_peak)
    leg_peaks.append(leg_peak)

print(f"  P6 peak (same as script 22):    {max(p6_peaks):.0f} veh/hr")
print(f"  Legacy peak (same df as P6):    {max(leg_peaks):.0f} veh/hr")
print(f"  Ratio P6/Legacy:                {max(p6_peaks)/max(leg_peaks):.3f}")
print(f"\n  Phase 2 reference used in script 22: 20,364 veh/hr")
print(f"  → Script 22 ratio: {max(p6_peaks)/20364:.3f}")
print(f"\n  If we compare P6 to LEGACY on SAME df:")
print(f"  → Same-run ratio: {max(p6_peaks)/max(leg_peaks):.3f}")

print("""
CONCLUSION:
If the same-run ratio is ~1.0, then the 0.68 was not a formula bug —
it was a comparison against a different reference point (Phase 2 script
that used different simulation parameters, probably single-lane or
different rates). The formula implementations are algebraically equivalent.
""")
