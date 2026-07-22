"""
Phase 6 — Definitive FD comparison: Phase 6 Eq 6-15 vs Phase 2 legacy,
with MATCHING simulation parameters (same rates, same duration, same
aggregation method, same result key).

Goal: produce an honest apples-to-apples comparison figure and document
the exact source of the 0.68 ratio.

Phase 2 (script 05) used:
  rates = [500, 1000, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 25000, 30000]
  duration_s = 1000
  window_s = 200
  result key = fd_dict['all']   <-- ALL modes, not per-mode
  aggregation = mean of stable windows (iloc[1:])
  single shared rng across all modes and rates

Script 22 used:
  rates = [200, 500, 800, ..., 12000]  <-- max 12,000, not 30,000
  duration_s = 1800
  window_s = 60
  result key = fd_dict['two_wheeler']  <-- per-mode
  aggregation = max flow across windows

These are different scenarios → comparing their peaks gives a meaningless ratio.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import (
    flow_density_by_mode,
    flow_density_by_mode_from_collector,
)

CONFIG_PATH = "configs/intersection_default.yaml"
config = load_config(CONFIG_PATH)
cell_length_m = config["grid"]["cell_length_m"]
road_length_m = config["midblock_test"]["road_length_m"]
road_length_cells = int(road_length_m / cell_length_m)
MODE_PARAMS = config["mode_params"]

# Exactly match Phase 2 parameters
RATES = [500, 1000, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 25000, 30000]
DURATION_S = 1000
WINDOW_S = 200
MODES = ["two_wheeler", "three_wheeler", "car", "bus"]
road_geometry = {"road_length_cells": road_length_cells, "cell_length_m": cell_length_m}

MODE_COLORS = {
    "two_wheeler":   "#e74c3c",
    "three_wheeler": "#f39c12",
    "car":           "#2980b9",
    "bus":           "#27ae60",
}

print("Running Phase 6 isolated-mode FD with Phase 2's EXACT parameters...")
print("(rates, duration, window, aggregation all match Phase 2 script 05)\n")

results_p6  = {m: [] for m in MODES}
results_leg = {m: [] for m in MODES}

# Use ONE shared rng exactly as Phase 2 did
rng = np.random.default_rng(42)

for target_mode in MODES:
    print(f"  Mode: {target_mode}")
    mode_mix = {m: (1.0 if m == target_mode else 0.0) for m in MODES}

    for r in RATES:
        df = run_midblock_simulation_multimode(config, r, DURATION_S, mode_mix, rng)

        # Phase 6 method
        fd_p6 = flow_density_by_mode_from_collector(
            df, road_geometry, window_s=WINDOW_S, mode_params=MODE_PARAMS
        )
        fd_p6_all = fd_p6.get("all", None)
        if fd_p6_all is not None and len(fd_p6_all) > 1:
            stable = fd_p6_all.iloc[1:]
            results_p6[target_mode].append((
                stable["density_veh_per_km"].mean(),
                stable["flow_veh_per_hr"].mean(),
            ))

        # Legacy Phase 2 method (exactly as script 05 did: fd_dict['all'])
        fd_leg = flow_density_by_mode(df, road_length_cells, cell_length_m, WINDOW_S)
        fd_leg_all = fd_leg.get("all", None)
        if fd_leg_all is not None and len(fd_leg_all) > 1:
            stable = fd_leg_all.iloc[1:]
            results_leg[target_mode].append((
                stable["density_veh_per_km"].mean(),
                stable["flow_veh_per_hr"].mean(),
            ))

# Compute and print peak capacities
print("\n=== PEAK CAPACITY COMPARISON (matching Phase 2 parameters) ===\n")
print(f"{'Mode':<15} {'P6 peak':>12} {'Legacy peak':>12} {'Ratio':>8} {'P2 ref (script 22)':>20}")
print("─" * 72)
phase2_ref_script22 = {"two_wheeler": 20364, "three_wheeler": 8958, "car": 4920, "bus": 1866}
for mode in MODES:
    p6_peak  = max([f for _, f in results_p6[mode]])  if results_p6[mode]  else 0
    leg_peak = max([f for _, f in results_leg[mode]]) if results_leg[mode] else 0
    ratio = p6_peak / leg_peak if leg_peak > 0 else 0
    ref = phase2_ref_script22[mode]
    print(f"{mode:<15} {p6_peak:>12.0f} {leg_peak:>12.0f} {ratio:>8.3f} {ref:>20.0f}")

print("""
Key: 'P2 ref (script 22)' = the reference hardcoded in script 22.
     When P2 parameters match, P6/Legacy ratio should be ~1.00.
     The ~0.68 came from script 22 comparing its max-flow-over-12000-veh/hr-runs
     against script 05's avg-flow-over-30000-veh/hr-runs.
""")

# ─── Plot ───────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle(
    "Phase 6: Apples-to-Apples FD Comparison\n"
    "(Same rates 500–30,000 · same duration 1000s · same window 200s · same rng)",
    fontsize=12, fontweight="bold"
)

for mode in MODES:
    if results_p6[mode]:
        d_p6, f_p6 = zip(*results_p6[mode])
        ax1.plot(d_p6, f_p6, marker="o", ms=5, label=mode, color=MODE_COLORS[mode])
    if results_leg[mode]:
        d_leg, f_leg = zip(*results_leg[mode])
        ax2.plot(d_leg, f_leg, marker="o", ms=5, label=mode, color=MODE_COLORS[mode])

ax1.set_title("Phase 6 · Eq 6-15 cell-occupancy", fontsize=11)
ax1.set_xlabel("Density (veh/km)"); ax1.set_ylabel("Flow (veh/hr)")
ax1.legend(fontsize=9); ax1.grid(alpha=0.3)

ax2.set_title("Legacy · Phase 2 method (avg records / km)", fontsize=11)
ax2.set_xlabel("Density (veh/km)"); ax2.set_ylabel("Flow (veh/hr)")
ax2.legend(fontsize=9); ax2.grid(alpha=0.3)

plt.tight_layout()
out = "notebooks/figures/phase6_post_refactor_fd_check.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"Updated figure saved: {out}")
