"""
Phase 7 — Calibration objective function (Eq 16).

Eq 16 from Singh & Ramachandra Rao (2023):
  E = sum_over_bins [ ((q_f - q_s) / q_f)^2  +  ((k_f - k_s) / k_f)^2 ]

where:
  q_f, q_s = field / simulated flow (veh/hr) per bin
  k_f, k_s = field / simulated density (veh/km) per bin

Bins with q_f or k_f near zero are excluded (epsilon guard) to avoid
division-by-zero distorting the objective — documented as bin exclusion,
not epsilon-substitution, per spec recommendation.

SCOPE NOTE (PHASE_REPORT.md):
This objective is calibrated against the Kanagaraj MIDBLOCK dataset
(data/processed/trajectories_kanagaraj.csv), not against intersection
data. The field data covers a ~242m unsignalised midblock stretch at 0.5s
resolution; the simulation uses a 1000m midblock scenario
(run_midblock_simulation_multimode) to match this context.

Parameters calibrated:
  MIDBLOCK-RELEVANT (calibrated against real field data):
    max_speed_cells_per_step, p_slowdown, lane_change_prob (×4 modes)

  LEFT AT PAPER TABLE 2 / LITERATURE VALUES (not observable in midblock data):
    max_accel_cells_per_step2, position_preference (lateral bias — needs
    full trajectory lateral analysis, out of scope for first calibration pass)
    IZOI parameters (intersection-specific, not present in midblock data)
    seepage safety margins (red-phase specific, midblock has no signal)

BUGS FIXED (Phase 7 re-calibration commit):
  Bug 1 (PRIMARY): calibration_objective previously hardcoded rate=2000 veh/hr
    while the Kanagaraj field data represents ~6066 veh/hr demand (3x mismatch).
    Fix: infer simulation demand rate from field_flow_density mean flow.
  Bug 2 (SECONDARY): flow_density_table used measurement_point_offset=50
    (25m from end of 1000m road) while field measures at midpoint of 243m road
    (121m). Fix: use offset = road_length_cells // 2 for both sides.
"""

from __future__ import annotations

import copy
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

from src.metrics.density_flow import flow_density_table


# Field data road is ~242.8m; simulation midblock is 1000m.
# Density and flow are both scale-invariant under Little's Law at matched demand:
# density [veh/km] = N_on_road / road_length_km; flow [veh/hr] = crossings × 3600/window_s.
# For these to be comparable, the simulation must run at the SAME demand rate as the field.

FLOW_ZERO_THRESHOLD = 10.0   # veh/hr below which a bin is excluded (q≈0)
DENSITY_ZERO_THRESHOLD = 0.5 # veh/km below which a bin is excluded (k≈0)


def build_field_fd(
    field_df: pd.DataFrame,
    window_s: int,
    road_length_m: float,
    cell_length_m: float,
) -> pd.DataFrame:
    """
    Compute flow/density time-series from the Kanagaraj field trajectory CSV.

    Field data schema: vehicle_id, mode, time_s, x_m, y_m, speed_mps
    Time step: 0.5s (but we aggregate into window_s bins).

    Density: average vehicles on road per second / road_length_km
    Flow: crossings of midpoint per window × 3600/window_s

    Parameters
    ----------
    field_df : pd.DataFrame
        Raw Kanagaraj trajectory data.
    window_s : int
        Window size in seconds (same as used for sim FD).
    road_length_m : float
        Road length inferred from field data (max x_m).
    cell_length_m : float
        Not used for field data (already in metres), kept for API symmetry.

    Returns
    -------
    pd.DataFrame with columns: time_window_start, time_window_end,
                                flow_veh_per_hr, density_veh_per_km
    """
    road_length_km = road_length_m / 1000.0
    meas_pt = road_length_m / 2.0  # midpoint

    # Pre-compute previous x_m globally per vehicle (same fix as Collector)
    field_sorted = field_df.sort_values(["vehicle_id", "time_s"])
    field_sorted = field_sorted.copy()
    field_sorted["_prev_x"] = field_sorted.groupby("vehicle_id")["x_m"].shift(1)

    t_min = field_df["time_s"].min()
    t_max = field_df["time_s"].max()
    windows = np.arange(t_min, t_max, window_s)
    if len(windows) < 2:
        return pd.DataFrame(columns=[
            "time_window_start", "time_window_end", "flow_veh_per_hr", "density_veh_per_km"
        ])

    results = []
    for i in range(len(windows) - 1):
        w_start = windows[i]
        w_end = windows[i + 1]
        mask = (field_sorted["time_s"] >= w_start) & (field_sorted["time_s"] < w_end)
        df_win = field_sorted[mask]

        if df_win.empty:
            continue

        # Density: avg vehicle-seconds / road_length_km
        avg_n = df_win.groupby("time_s")["vehicle_id"].nunique().mean()
        density = avg_n / road_length_km

        # Flow: crossings of measurement midpoint
        crossed = df_win[
            (df_win["x_m"] >= meas_pt) &
            (df_win["_prev_x"] < meas_pt)
        ]
        n_crossings = crossed["vehicle_id"].nunique()
        flow = n_crossings * (3600.0 / window_s)

        results.append({
            "time_window_start": float(w_start),
            "time_window_end": float(w_end),
            "flow_veh_per_hr": flow,
            "density_veh_per_km": density,
        })

    return pd.DataFrame(results)


def calibration_objective(
    params: Dict[str, Any],
    config_template: Dict[str, Any],
    field_flow_density: pd.DataFrame,
    rng_seed: int = 42,
    window_s: int = 300,  # 5-minute bins per spec
) -> float:
    """
    Eq 16 calibration objective.

    Parameters
    ----------
    params : dict
        Parameter overrides to apply to config_template.
        Structure: {"mode_params": {"two_wheeler": {"max_speed_cells_per_step": 28, ...}, ...}}
        Any key not present is left at its template value.
    config_template : dict
        Full config dict (never mutated).
    field_flow_density : pd.DataFrame
        Pre-computed field FD table (from build_field_fd).
        Columns: time_window_start, time_window_end, flow_veh_per_hr, density_veh_per_km
    rng_seed : int
        Seed for reproducible simulation runs.
    window_s : int
        FD aggregation window in seconds.

    Returns
    -------
    float
        Eq 16 error (lower = better fit). Returns a large penalty if
        the simulation produces no usable output.
    """
    import numpy as np
    from src.sim.sim_loop import run_midblock_simulation_multimode

    # --- Merge params into a deep copy of config ---
    cfg = copy.deepcopy(config_template)
    if "mode_params" in params:
        for mode, mode_overrides in params["mode_params"].items():
            if mode in cfg.get("mode_params", {}):
                cfg["mode_params"][mode].update(mode_overrides)

    # --- Determine simulation duration from field data time range ---
    duration_s = int(
        field_flow_density["time_window_end"].max() -
        field_flow_density["time_window_start"].min()
    )
    duration_s = max(duration_s, window_s * 2)  # at least 2 windows

    # --- Infer mode mix from config (real Kanagaraj proportions) ---
    mode_mix = {
        "two_wheeler":   0.546,
        "car":           0.267,
        "three_wheeler": 0.151,
        "bus":           0.036,
    }

    # --- BUG 1 FIX: infer simulation demand rate from field data ---
    # Previously hardcoded as 2000 veh/hr — 3x below field demand (~6066 veh/hr).
    # The mean flow in the field FD table is the best single-number estimate of
    # the field's arrival rate.  Clamped to [1000, 10000] as a sanity guard.
    field_mean_flow = float(field_flow_density["flow_veh_per_hr"].mean())
    sim_rate = int(np.clip(field_mean_flow, 1000, 10000))

    rng = np.random.default_rng(rng_seed)
    try:
        sim_df = run_midblock_simulation_multimode(cfg, sim_rate, duration_s, mode_mix, rng)
    except Exception:
        return 1e9  # penalty for crash

    if sim_df is None or sim_df.empty:
        return 1e9

    cell_length_m = cfg["grid"]["cell_length_m"]
    road_length_cells = int(cfg["midblock_test"]["road_length_m"] / cell_length_m)
    road_geometry = {"road_length_cells": road_length_cells, "cell_length_m": cell_length_m}

    # --- BUG 2 FIX: measurement point at center of sim road ---
    # Previously offset=50 (25m from end of 1000m road) — far from field's midpoint.
    # Field measures at midpoint of 243m road (121m).  Use road center (offset = half
    # road length in cells) so both sides measure at comparable relative positions.
    meas_offset = road_length_cells // 2  # = 1000 cells from end = center of 1000m road

    sim_fd_all = flow_density_table(
        sim_df, road_geometry,
        window_s=window_s,
        mode_params=cfg.get("mode_params"),
        measurement_point_offset=meas_offset,
    )
    # Use "all" aggregated row
    sim_fd = sim_fd_all[sim_fd_all["mode"] == "all"] if not sim_fd_all.empty else sim_fd_all

    if sim_fd.empty:
        return 1e9

    # --- Align field and sim FD by window index (they may differ in length) ---
    n_bins = min(len(field_flow_density), len(sim_fd))
    if n_bins == 0:
        return 1e9

    q_f = field_flow_density["flow_veh_per_hr"].values[:n_bins]
    k_f = field_flow_density["density_veh_per_km"].values[:n_bins]
    q_s = sim_fd["flow_veh_per_hr"].values[:n_bins]
    k_s = sim_fd["density_veh_per_km"].values[:n_bins]

    # --- Eq 16: sum of squared relative errors, excluding near-zero bins ---
    error = 0.0
    n_used = 0
    for qf, kf, qs, ks in zip(q_f, k_f, q_s, k_s):
        if qf < FLOW_ZERO_THRESHOLD or kf < DENSITY_ZERO_THRESHOLD:
            continue  # exclude bin (documented: bin exclusion, not epsilon)
        err_flow    = ((qf - qs) / qf) ** 2
        err_density = ((kf - ks) / kf) ** 2
        error += err_flow + err_density
        n_used += 1

    if n_used == 0:
        return 1e9  # no usable bins

    return float(error)
