"""
Phase 6 FD ordering investigation:
The mixed-traffic per-mode FD shows car > three_wheeler in flow,
but Phase 2 isolated-mode tests showed three_wheeler > car.

Root cause hypothesis: in MIXED traffic, per-mode flow is bounded by
(mode_proportion × total_flow), not by isolated-mode capacity.
  - car proportion   = 26.7%  → car flow   ≈ 0.267 × total
  - 3W proportion    = 15.1%  → 3W flow    ≈ 0.151 × total

So car > 3W in flow purely because of proportion, even if 3W capacity > car capacity.

DIAGNOSTIC: Run ISOLATED single-mode simulations through the new Phase 6
Collector + flow_density_by_mode_from_collector() and check ordering.
If isolated ordering is two_wheeler > three_wheeler > car > bus, the refactor
is correct and the mixed-traffic ordering difference is purely methodological.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import flow_density_by_mode_from_collector

CONFIG_PATH = "configs/intersection_default.yaml"
config = load_config(CONFIG_PATH)
cell_length_m = config["grid"]["cell_length_m"]
road_length_m = config["midblock_test"]["road_length_m"]
road_length_cells = int(road_length_m / cell_length_m)
MODE_PARAMS = config["mode_params"]

MODES = ["two_wheeler", "three_wheeler", "car", "bus"]
DURATION_S = 1800
RATES = [200, 500, 800, 1200, 1800, 2500, 3500, 5000, 8000, 12000]

road_geometry = {"road_length_cells": road_length_cells, "cell_length_m": cell_length_m}

print("=== ISOLATED single-mode FDs through Phase 6 Collector ===\n")
isolated_peaks = {}
isolated_data = {mode: {"density": [], "flow": []} for mode in MODES}

for mode in MODES:
    isolated_mix = {mode: 1.0}  # 100% of this mode
    print(f"Mode: {mode}")
    for rate in RATES:
        rng = np.random.default_rng(seed=42)
        df = run_midblock_simulation_multimode(config, rate, DURATION_S, isolated_mix, rng)
        fd = flow_density_by_mode_from_collector(df, road_geometry, window_s=60, mode_params=MODE_PARAMS)
        if mode in fd:
            d = fd[mode]["density_veh_per_km"].values
            f = fd[mode]["flow_veh_per_hr"].values
            isolated_data[mode]["density"].extend(d.tolist())
            isolated_data[mode]["flow"].extend(f.tolist())
    peak = max(isolated_data[mode]["flow"]) if isolated_data[mode]["flow"] else 0
    isolated_peaks[mode] = peak
    print(f"  Peak isolated flow: {peak:.0f} veh/hr")

print("\nIsolated capacity ordering (Phase 6 Eq 6-15 cell-occupancy):")
ordered = sorted(isolated_peaks.items(), key=lambda x: -x[1])
for i, (m, f) in enumerate(ordered):
    print(f"  {i+1}. {m}: {f:.0f} veh/hr")

expected = ["two_wheeler", "three_wheeler", "car", "bus"]
actual = [m for m, _ in ordered]
if actual == expected:
    print("\n✓ MATCH: Isolated ordering = two_wheeler > three_wheeler > car > bus")
    print("  Mixed-traffic ordering (car > 3W) is a proportion artifact, not a bug.")
else:
    print(f"\n✗ MISMATCH in isolated ordering: {actual}")
    print("  This would indicate a real problem in the refactor.")

# Plot isolated FD for comparison with Phase 2 reference values
MODE_COLORS = {"two_wheeler": "#e74c3c", "three_wheeler": "#f39c12", "car": "#2980b9", "bus": "#27ae60"}
fig, ax = plt.subplots(figsize=(8, 6))
for mode in MODES:
    d = np.array(isolated_data[mode]["density"])
    f = np.array(isolated_data[mode]["flow"])
    mask = (d > 0) | (f > 0)
    ax.scatter(d[mask], f[mask], s=8, alpha=0.5, color=MODE_COLORS[mode],
               label=f"{mode} (peak {isolated_peaks[mode]:.0f})")
ax.set_xlabel("Density (veh/km)")
ax.set_ylabel("Flow (veh/hr)")
ax.set_title("Phase 6: Isolated-Mode FD Check (Eq 6-15)\nCompare with Phase 2 reference values")
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig("notebooks/figures/phase6_isolated_mode_fd_check.png", dpi=150)
print("\nSaved: notebooks/figures/phase6_isolated_mode_fd_check.png")

print("\nPhase 2 reference capacities vs Phase 6:")
phase2_ref = {"two_wheeler": 20364, "three_wheeler": 8958, "car": 4920, "bus": 1866}
for mode in MODES:
    p6 = isolated_peaks[mode]
    p2 = phase2_ref[mode]
    ratio = p6/p2 if p2 > 0 else 0
    print(f"  {mode:<15}: P6={p6:>7.0f} | P2={p2:>6} | ratio={ratio:.2f}")
