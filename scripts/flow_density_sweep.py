"""
flow_density_sweep.py — Stage 1 flow-density verification script.

Sweeps density from 0.05 to 0.95 (19 values), periodic boundary,
500-cell road, 1000 warm-up steps + 500 measurement steps per density.

Also prints variance and seed-independence data explicitly.

Usage:
    .venv/bin/python simulator/scripts/flow_density_sweep.py
"""

from __future__ import annotations

import sys
import os
import json

import numpy as np
import matplotlib
matplotlib.use("Agg")   # non-interactive backend for headless runs
import matplotlib.pyplot as plt

# Allow running from repo root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.cell import random_initial_state
from src.core.rule184 import run, run_collect
from src.analytics.density import measure_flow

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
ROAD_LEN   = 500
WARMUP     = 1000
MEASURE    = 500
DENSITIES  = np.linspace(0.05, 0.95, 19)
SEED_A     = 42
SEED_B     = 7777   # second seed for independence check


def sweep(seed: int):
    """Run the sweep for a given seed. Returns arrays of (rho, mean_f, std_f)."""
    rhos, means, stds = [], [], []
    for rho in DENSITIES:
        rng = np.random.default_rng(seed)
        state = random_initial_state(ROAD_LEN, rho, rng)
        state = run(state, WARMUP, periodic=True)
        history = run_collect(state, MEASURE, periodic=True)
        mean_f, std_f = measure_flow(history)
        rhos.append(rho)
        means.append(mean_f)
        stds.append(std_f)
    return np.array(rhos), np.array(means), np.array(stds)


def main():
    print("=" * 60)
    print("Flow-density sweep — Rule 184, periodic, 500 cells")
    print(f"Warm-up: {WARMUP} steps | Measurement: {MEASURE} steps")
    print("=" * 60)

    rhos_a, means_a, stds_a = sweep(SEED_A)
    rhos_b, means_b, stds_b = sweep(SEED_B)

    theory = np.minimum(rhos_a, 1 - rhos_a)

    print(f"\n{'ρ':>6}  {'theory':>10}  {'measured_A':>12}  {'std_A':>12}  {'measured_B':>12}  {'|A-B|':>10}  {'|meas-theory|':>14}")
    print("-" * 90)
    max_err = 0.0
    max_std = 0.0
    max_seed_diff = 0.0
    for i, rho in enumerate(rhos_a):
        err   = abs(means_a[i] - theory[i])
        sdiff = abs(means_a[i] - means_b[i])
        max_err = max(max_err, err)
        max_std = max(max_std, stds_a[i])
        max_seed_diff = max(max_seed_diff, sdiff)
        print(f"{rho:>6.3f}  {theory[i]:>10.8f}  {means_a[i]:>12.8f}  {stds_a[i]:>12.2e}  "
              f"{means_b[i]:>12.8f}  {sdiff:>10.2e}  {err:>14.2e}")

    print("-" * 90)
    print(f"\nSummary:")
    print(f"  Max |measured - theory|  : {max_err:.2e}")
    print(f"  Max std (seed A)         : {max_std:.2e}")
    print(f"  Max |seed A - seed B|    : {max_seed_diff:.2e}")
    print()

    if max_err < 1e-6:
        print("✅ PASS: flow matches min(ρ,1-ρ) within 1e-6")
    else:
        print(f"❌ FAIL: max error {max_err:.2e} exceeds 1e-6")

    if max_std < 1e-12:
        print("✅ PASS: zero variance at steady state (std < 1e-12)")
    else:
        print(f"❌ FAIL: non-zero variance at steady state (max std={max_std:.2e})")

    if max_seed_diff < 1e-9:
        print("✅ PASS: seed-independent (|A-B| < 1e-9 everywhere)")
    else:
        print(f"❌ FAIL: seed-dependent (max |A-B|={max_seed_diff:.2e})")

    # -----------------------------------------------------------------------
    # Plot
    # -----------------------------------------------------------------------
    rho_fine = np.linspace(0, 1, 500)
    theory_fine = np.minimum(rho_fine, 1 - rho_fine)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(rho_fine, theory_fine, "k-", linewidth=2.0,
            label=r"Theory: $\min(\rho,\,1-\rho)$", zorder=2)
    ax.scatter(rhos_a, means_a, color="#E05C2A", s=60, zorder=3,
               label=f"Measured (seed {SEED_A}, N={ROAD_LEN})", marker="o")
    ax.scatter(rhos_b, means_b, color="#2A7FE0", s=30, zorder=4,
               label=f"Measured (seed {SEED_B})", marker="^", alpha=0.7)

    ax.set_xlabel(r"Density $\rho$", fontsize=12)
    ax.set_ylabel(r"Flow $q$ (vehicles / cell / step)", fontsize=12)
    ax.set_title("Rule 184 Flow-Density Curve\n"
                 r"Periodic BC, $N=500$, warm-up=1000, measure=500",
                 fontsize=11)
    ax.legend(fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 0.55)
    ax.grid(True, alpha=0.3)

    # Annotate max error
    ax.text(0.02, 0.48,
            f"Max error vs theory: {max_err:.2e}\n"
            f"Max std at steady state: {max_std:.2e}\n"
            f"Max seed-A vs seed-B diff: {max_seed_diff:.2e}",
            fontsize=8, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs",
                            "stage1_flow_density.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved to: {os.path.abspath(out_path)}")

    # Also save raw numbers as JSON for traceability
    data = {
        "densities": rhos_a.tolist(),
        "theory": theory.tolist(),
        "measured_seed_A": means_a.tolist(),
        "std_seed_A": stds_a.tolist(),
        "measured_seed_B": means_b.tolist(),
        "max_error_vs_theory": float(max_err),
        "max_std": float(max_std),
        "max_seed_diff": float(max_seed_diff),
    }
    json_path = out_path.replace(".png", ".json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Data  saved to: {os.path.abspath(json_path)}")


if __name__ == "__main__":
    main()
