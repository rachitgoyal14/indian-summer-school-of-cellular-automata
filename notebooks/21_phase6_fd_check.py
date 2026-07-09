"""
Phase 6 validation: post-refactor FD check.

Runs ~30-minute (1800s) multimode midblock simulation through the NEW
flow_density_table() function (Eq 6-15 cell-occupancy) and plots the
FD by mode.

The resulting figure should qualitatively match Phase 2's FD ordering:
  two_wheeler > three_wheeler > car > bus  (both capacity and jam density)

Save to: notebooks/figures/phase6_post_refactor_fd_check.png
Also export trajectory CSV: data/processed/sim_trajectories_phase6_baseline.csv
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.sim.collector import Collector
from src.metrics.density_flow import flow_density_by_mode_from_collector, flow_density_by_mode
from src.metrics.trajectory_export import export_trajectories

CONFIG_PATH = "configs/intersection_default.yaml"
config = load_config(CONFIG_PATH)

cell_length_m = config["grid"]["cell_length_m"]
cell_width_m  = config["grid"]["cell_width_m"]
road_length_m = config["midblock_test"]["road_length_m"]
road_length_cells = int(road_length_m / cell_length_m)

MODE_MIX = {
    "two_wheeler": 0.546,
    "car": 0.267,
    "three_wheeler": 0.151,
    "bus": 0.036,
}
MODES = list(MODE_MIX.keys())
MODE_PARAMS = config["mode_params"]

DURATION_S = 1800       # ~30 minutes simulation
WINDOW_S   = 60         # 1-minute windows
RATES = [200, 500, 800, 1200, 1800, 2500, 3500, 5000, 7000, 10000]  # veh/hr

print("Phase 6 FD Check — sweeping arrival rates...")
all_results = {mode: {"density": [], "flow": []} for mode in MODES + ["all"]}

for rate in RATES:
    print(f"  Rate {rate} veh/hr ... ", end="", flush=True)
    rng = np.random.default_rng(seed=42)
    df = run_midblock_simulation_multimode(config, rate, DURATION_S, MODE_MIX, rng)
    print(f"{len(df)} rows", end="", flush=True)

    road_geometry = {
        "road_length_cells": road_length_cells,
        "cell_length_m": cell_length_m,
    }

    # Use the Phase 6 cell-occupancy API
    fd_by_mode = flow_density_by_mode_from_collector(
        df, road_geometry, window_s=WINDOW_S, mode_params=MODE_PARAMS
    )

    for mode in MODES + ["all"]:
        if mode in fd_by_mode:
            fd = fd_by_mode[mode]
            all_results[mode]["density"].extend(fd["density_veh_per_km"].tolist())
            all_results[mode]["flow"].extend(fd["flow_veh_per_hr"].tolist())
    print("  ✓")

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle(
    "Phase 6: Post-Refactor Fundamental Diagram Check\n"
    "(Cell-Occupancy Eq 6-15 | Real Kanagaraj Mode Mix)",
    fontsize=13, fontweight="bold"
)

MODE_COLORS = {
    "two_wheeler":   "#e74c3c",
    "three_wheeler": "#f39c12",
    "car":           "#2980b9",
    "bus":           "#27ae60",
    "all":           "#8e44ad",
}
MODE_LABELS = {
    "two_wheeler":   "Two-Wheeler (54.6%)",
    "three_wheeler": "Three-Wheeler (15.1%)",
    "car":           "Car (26.7%)",
    "bus":           "Bus (3.6%)",
    "all":           "Mixed (all modes)",
}

ax_fd = axes[0]
ax_flow = axes[1]

for mode in MODES:
    d = np.array(all_results[mode]["density"])
    f = np.array(all_results[mode]["flow"])
    mask = (d > 0) | (f > 0)
    ax_fd.scatter(d[mask], f[mask], s=6, alpha=0.4, color=MODE_COLORS[mode],
                  label=MODE_LABELS[mode])

ax_fd.set_xlabel("Density (veh/km)", fontsize=11)
ax_fd.set_ylabel("Flow (veh/hr)", fontsize=11)
ax_fd.set_title("FD by Mode (Phase 6 cell-occupancy method)", fontsize=11)
ax_fd.legend(fontsize=8, markerscale=2)
ax_fd.grid(alpha=0.3)

# Also plot using legacy Phase 1/2 API for comparison
print("\nComputing legacy FD for comparison panel...")
fd_legacy = flow_density_by_mode(df, road_length_cells, cell_length_m, WINDOW_S)
for mode in MODES:
    if mode in fd_legacy:
        d_leg = fd_legacy[mode]["density_veh_per_km"].values
        f_leg = fd_legacy[mode]["flow_veh_per_hr"].values
        mask = (d_leg > 0) | (f_leg > 0)
        ax_flow.scatter(d_leg[mask], f_leg[mask], s=6, alpha=0.4,
                        color=MODE_COLORS[mode], label=MODE_LABELS[mode])

ax_flow.set_xlabel("Density (veh/km)", fontsize=11)
ax_flow.set_ylabel("Flow (veh/hr)", fontsize=11)
ax_flow.set_title("FD by Mode (Legacy Phase 2 method — for comparison)", fontsize=11)
ax_flow.legend(fontsize=8, markerscale=2)
ax_flow.grid(alpha=0.3)

plt.tight_layout()
out_fig = "notebooks/figures/phase6_post_refactor_fd_check.png"
plt.savefig(out_fig, dpi=150, bbox_inches="tight")
print(f"\nSaved: {out_fig}")

# ---------------------------------------------------------------------------
# Print max flow per mode for comparison with Phase 2 reference values
# ---------------------------------------------------------------------------
print("\n=== Phase 6 vs Phase 2 capacity comparison ===")
phase2_ref = {
    "two_wheeler": 20364,
    "three_wheeler": 8958,
    "car": 4920,
    "bus": 1866,
}
for mode in MODES:
    f_arr = np.array(all_results[mode]["flow"])
    max_f = f_arr.max() if len(f_arr) > 0 else 0.0
    ref = phase2_ref.get(mode, 0)
    print(f"  {mode:<15}: Phase 6 peak = {max_f:>8.0f} veh/hr  |  Phase 2 ref = {ref:>6} veh/hr")

# Check ordering
flows = {mode: np.array(all_results[mode]["flow"]).max() if all_results[mode]["flow"] else 0
         for mode in MODES}
print("\nCapacity ordering check:")
ordered = sorted(flows.items(), key=lambda x: -x[1])
for i, (m, f) in enumerate(ordered):
    print(f"  {i+1}. {m}: {f:.0f} veh/hr")
expected_order = ["two_wheeler", "three_wheeler", "car", "bus"]
actual_order = [m for m, _ in ordered]
if actual_order == expected_order:
    print("\n✓ Ordering matches Phase 2: two_wheeler > three_wheeler > car > bus")
else:
    print(f"\n⚠ Ordering MISMATCH: {actual_order} (expected {expected_order})")

# ---------------------------------------------------------------------------
# Export trajectory CSV (highest-rate run for richness)
# ---------------------------------------------------------------------------
print("\nExporting trajectory CSV (rate=10000 veh/hr run)...")
rng2 = np.random.default_rng(seed=99)
df_export = run_midblock_simulation_multimode(config, 10000, DURATION_S, MODE_MIX, rng2)
traj_path = "data/processed/sim_trajectories_phase6_baseline.csv"
export_trajectories(df_export, traj_path, cell_length_m, cell_width_m)
print(f"Done. Rows in CSV: {len(df_export)}")
