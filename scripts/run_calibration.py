#!/usr/bin/env python3
"""
Phase 7 — Calibration CLI entry point.

Usage:
  python scripts/run_calibration.py [--full] [--pop N] [--gen N] [--seed S]

Loads intersection_default.yaml + Kanagaraj field data, runs two-stage
calibration (NSGA-II → Nelder-Mead), writes calibrated parameters to
configs/intersection_calibrated.yaml (never overwrites intersection_default.yaml).
"""
import argparse
import sys
import os
import copy
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import load_config
from src.calibration.optimizer import run_calibration, MODES


FIELD_DATA_PATH = "data/processed/trajectories_kanagaraj.csv"
OUTPUT_CONFIG   = "configs/intersection_calibrated.yaml"
CONVERGENCE_CSV = "data/processed/calibration_convergence.csv"


def build_calibrated_config(base_config: dict, best_params: dict) -> dict:
    """Merge calibrated mode_params into a copy of base_config."""
    cfg = copy.deepcopy(base_config)
    if "mode_params" in best_params:
        for mode, overrides in best_params["mode_params"].items():
            if mode in cfg.get("mode_params", {}):
                cfg["mode_params"][mode].update(overrides)
    # Store calibration metadata
    cfg["_calibration_meta"] = best_params.get("_meta", {})
    return cfg


def print_parameter_comparison(base_config: dict, calibrated_config: dict):
    """Print before/after parameter table."""
    params_of_interest = ["max_speed_cells_per_step", "p_slowdown", "lane_change_prob",
                          "max_accel_cells_per_step2"]
    print("\n" + "=" * 72)
    print("PARAMETER COMPARISON: Default vs Calibrated")
    print("=" * 72)
    print(f"{'Parameter':<35} {'Mode':<15} {'Default':>10} {'Calibrated':>12}")
    print("-" * 72)
    for param in params_of_interest:
        for mode in MODES:
            default_val = base_config.get("mode_params", {}).get(mode, {}).get(param, "—")
            calib_val   = calibrated_config.get("mode_params", {}).get(mode, {}).get(param, "—")
            changed = " *" if default_val != calib_val else ""
            print(f"  {param:<33} {mode:<15} {str(default_val):>10} {str(calib_val):>12}{changed}")
    print()

    # Mode ordering check
    print("Mode ordering check (max_speed_cells_per_step, must be TW ≥ 3W ≥ CAR ≥ BUS):")
    mode_speeds = {
        m: calibrated_config.get("mode_params", {}).get(m, {}).get("max_speed_cells_per_step", 0)
        for m in MODES
    }
    ordered = sorted(mode_speeds.items(), key=lambda x: -x[1])
    for i, (m, v) in enumerate(ordered):
        print(f"  {i+1}. {m}: {v}")
    tw  = mode_speeds.get("two_wheeler", 0)
    tw3 = mode_speeds.get("three_wheeler", 0)
    car = mode_speeds.get("car", 0)
    bus = mode_speeds.get("bus", 0)
    order_ok = tw >= tw3 >= car >= bus
    print(f"  Ordering preserved: {'✓' if order_ok else '✗ VIOLATION — INVESTIGATE'}")


def main():
    parser = argparse.ArgumentParser(description="Phase 7 calibration")
    parser.add_argument("--full",  action="store_true", help="Use full 20-dim parameter space")
    parser.add_argument("--pop",   type=int, default=30,  help="GA population size")
    parser.add_argument("--gen",   type=int, default=20,  help="GA generations")
    parser.add_argument("--nm",    type=int, default=50,  help="Nelder-Mead max iterations")
    parser.add_argument("--seed",  type=int, default=42,  help="RNG seed")
    parser.add_argument("--window", type=int, default=300, help="FD window in seconds")
    parser.add_argument("--config", default="configs/intersection_default.yaml")
    args = parser.parse_args()

    base_config = load_config(args.config)

    best_params = run_calibration(
        config_template   = base_config,
        field_data_path   = FIELD_DATA_PATH,
        reduced_mode      = not args.full,
        pop_size          = args.pop,
        n_gen             = args.gen,
        nm_max_iter       = args.nm,
        window_s          = args.window,
        rng_seed          = args.seed,
        convergence_csv   = CONVERGENCE_CSV,
        verbose           = True,
    )

    calibrated_config = build_calibrated_config(base_config, best_params)

    with open(OUTPUT_CONFIG, "w") as f:
        yaml.dump(calibrated_config, f, default_flow_style=False, sort_keys=False)

    print(f"\nCalibrated config written to: {OUTPUT_CONFIG}")
    print_parameter_comparison(base_config, calibrated_config)

    meta = best_params.get("_meta", {})
    print(f"\nFinal objective (Eq 16): {meta.get('best_f_nm', '?'):.5f}")
    print(f"Wall-clock time: {meta.get('wall_time_s', 0):.1f}s "
          f"({meta.get('wall_time_s', 0)/60:.1f} min)")
    print(f"Convergence log: {CONVERGENCE_CSV}")


if __name__ == "__main__":
    main()
