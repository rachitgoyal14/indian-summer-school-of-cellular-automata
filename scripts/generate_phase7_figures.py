#!/usr/bin/env python3
"""
Phase 7 figure generation script.

Produces:
  figures/phase7_convergence.png   — GA + Nelder-Mead convergence curve
  figures/phase7_fd_comparison.png — Default vs calibrated FD overlay
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─────────────────────────────────────────────────────────────────────────────
# 1. Convergence plot (GA generations + Nelder-Mead refinement)
# ─────────────────────────────────────────────────────────────────────────────

conv = pd.read_csv("data/processed/calibration_convergence.csv")

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle(
    "Phase 7 Calibration — Two-Stage Convergence\n"
    "(NSGA-II global → Nelder-Mead local refinement, reduced_mode=True, 12-dim)",
    fontsize=11, fontweight="bold"
)

# Panel A: objective vs generation (GA stage only)
ax = axes[0]
ax.plot(conv["generation"], conv["best_objective"], "o-",
        color="#2c7bb6", linewidth=2, markersize=5, label="Best objective (GA)")
ax.axhline(9.478494, color="#d7191c", linestyle="--", linewidth=1.5,
           label=f"NM final = 9.4785")
ax.set_xlabel("GA Generation", fontsize=11)
ax.set_ylabel("Eq 16 Objective E (lower = better)", fontsize=11)
ax.set_title("Stage 1: NSGA-II (pop=30, 20 gen)", fontsize=10)
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
ax.set_ylim(9.4, 10.6)

# Annotate plateau regions
# Gens 4-8: no improvement (plateau)
ax.axvspan(3.5, 8.5, alpha=0.08, color="orange", label="Plateau zone")
ax.annotate("Plateau\n(4 gen no improvement)",
            xy=(6, 9.68), fontsize=8, ha="center",
            color="darkorange",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="wheat", alpha=0.7))

# Panel B: objective vs wall-clock time
ax2 = axes[1]
ax2.plot(conv["wall_time_s"] / 60, conv["best_objective"], "o-",
         color="#1a9641", linewidth=2, markersize=5, label="GA best objective")
ax2.axhline(9.593623, color="#2c7bb6", linestyle=":", linewidth=1.5,
            label=f"GA final = 9.5936")
ax2.axhline(9.478494, color="#d7191c", linestyle="--", linewidth=1.5,
            label=f"NM final = 9.4785")

# Mark NM region (after GA ends at ~21.6 min, NM wall time est)
ga_wall_min = conv["wall_time_s"].iloc[-1] / 60  # 21.6 min
nm_wall_min = 1883.13 / 60                        # total from meta
ax2.axvspan(ga_wall_min, nm_wall_min, alpha=0.12, color="#d7191c")
ax2.annotate(f"NM stage\n({nm_wall_min - ga_wall_min:.0f} min)",
             xy=((ga_wall_min + nm_wall_min) / 2, 9.52), fontsize=8,
             ha="center", color="darkred",
             bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffe5e5", alpha=0.8))
ax2.annotate(f"GA stage\n({ga_wall_min:.0f} min)",
             xy=(ga_wall_min / 2, 10.3), fontsize=8,
             ha="center", color="darkgreen",
             bbox=dict(boxstyle="round,pad=0.2", facecolor="#e5ffe5", alpha=0.8))

ax2.set_xlabel("Wall-clock time (minutes)", fontsize=11)
ax2.set_ylabel("Eq 16 Objective E", fontsize=11)
ax2.set_title("Objective vs Wall-Clock Time", fontsize=10)
ax2.legend(fontsize=9)
ax2.grid(True, alpha=0.3)
ax2.set_ylim(9.4, 10.6)

plt.tight_layout()
out_path = "figures/phase7_convergence.png"
plt.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out_path}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Field FD vs default simulation FD vs calibrated simulation FD
# ─────────────────────────────────────────────────────────────────────────────
from src.core.config import load_config
from src.calibration.objective import build_field_fd
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import flow_density_table
import copy

config_default = load_config("configs/intersection_default.yaml")
config_calib   = load_config("configs/intersection_calibrated.yaml")

field_df = pd.read_csv("data/processed/trajectories_kanagaraj.csv")
road_length_m = float(field_df["x_m"].max())
cell_length_m = config_default["grid"]["cell_length_m"]

WINDOW_S = 300
field_fd = build_field_fd(field_df, WINDOW_S, road_length_m, cell_length_m)

MODE_MIX = {"two_wheeler": 0.546, "car": 0.267, "three_wheeler": 0.151, "bus": 0.036}
DURATION = 600  # 10 min — faster diagnostic
RATE = 2000
rng_default = np.random.default_rng(42)
rng_calib   = np.random.default_rng(42)

print("Running default sim...")
sim_df_def = run_midblock_simulation_multimode(config_default, RATE, DURATION, MODE_MIX, rng_default)
road_len_cells = int(config_default["midblock_test"]["road_length_m"] / cell_length_m)
road_geom = {"road_length_cells": road_len_cells, "cell_length_m": cell_length_m}

fd_def = flow_density_table(sim_df_def, road_geom, WINDOW_S,
                            mode_params=config_default.get("mode_params"))
fd_def_all = fd_def[fd_def["mode"] == "all"]

print("Running calibrated sim...")
sim_df_cal = run_midblock_simulation_multimode(config_calib, RATE, DURATION, MODE_MIX, rng_calib)
fd_cal = flow_density_table(sim_df_cal, road_geom, WINDOW_S,
                            mode_params=config_calib.get("mode_params"))
fd_cal_all = fd_cal[fd_cal["mode"] == "all"]

print(f"  Field FD: {len(field_fd)} bins,  Default sim FD: {len(fd_def_all)} bins,  Calibrated sim FD: {len(fd_cal_all)} bins")

fig2, ax = plt.subplots(figsize=(9, 6))
ax.scatter(field_fd["density_veh_per_km"], field_fd["flow_veh_per_hr"],
           s=120, color="black", zorder=5, marker="D", label="Field (Kanagaraj)")
ax.scatter(fd_def_all["density_veh_per_km"], fd_def_all["flow_veh_per_hr"],
           s=80, color="#2c7bb6", alpha=0.8, marker="o", label="Sim: Default params")
ax.scatter(fd_cal_all["density_veh_per_km"], fd_cal_all["flow_veh_per_hr"],
           s=80, color="#d7191c", alpha=0.8, marker="^", label="Sim: Calibrated params")
ax.set_xlabel("Density (veh/km)", fontsize=12)
ax.set_ylabel("Flow (veh/hr)", fontsize=12)
ax.set_title(
    "Phase 7 — Field vs Simulation FD Comparison\n"
    "(Midblock, 300s windows, all-mode aggregate, rate=2000 veh/hr, 10 min sim)",
    fontsize=10
)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
out2 = "figures/phase7_fd_comparison.png"
fig2.tight_layout()
fig2.savefig(out2, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out2}")
print("Done.")
