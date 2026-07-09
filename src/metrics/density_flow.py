"""
Phase 6 — Formalized density/flow metrics using the paper's cell-occupancy method.

Implements Eq 6-15 from Singh & Ramachandra Rao (2023):
  density = (occupied cells / total cells) × (1 / avg_vehicle_footprint_cells) × (1000 / cell_length_m)
  flow    = crossings_in_window × (3600 / window_s)

CRITICAL: all cell-size references must come from the SAME config object used
everywhere else (grid, gaps, seepage, density_flow) — see test_cell_size_consistency.py.
This module intentionally does NOT hardcode cell_length_m or cell_width_m.

Public API (for calibration and validation phases):
  density_veh_per_km(occupied_cells, total_cells, avg_vehicle_footprint_cells, cell_length_m)
  flow_veh_per_hr(crossings_in_window, window_s)
  flow_density_table(collector_df, road_geometry, window_s) → pd.DataFrame
  flow_density_by_mode_from_collector(collector_df, road_geometry, window_s) → dict[str, pd.DataFrame]

Legacy API (kept for Phase 1/2 regression tests):
  flow_density_from_log(df, road_length_cells, cell_length_m, window_s, ...)
  flow_density_by_mode(df, road_length_cells, cell_length_m, window_s, ...)
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Primitive Eq 6-15 functions
# ---------------------------------------------------------------------------

def density_veh_per_km(
    occupied_cells: int,
    total_cells: int,
    avg_vehicle_footprint_cells: float,
    cell_length_m: float,
) -> float:
    """
    Convert cell occupancy to macroscopic density in veh/km.

    Per Eq 6-15 (cell-occupancy method):
      occupancy_ratio = occupied_cells / total_cells
      density_veh_per_cell_length = occupancy_ratio / avg_vehicle_footprint_cells
      density_veh_per_km = density_veh_per_cell_length * (1000.0 / cell_length_m)

    Parameters
    ----------
    occupied_cells : int
        Number of longitudinal cells occupied by vehicle bodies in this window.
    total_cells : int
        Total number of longitudinal cells on the road segment being measured.
    avg_vehicle_footprint_cells : float
        Average vehicle length in cells (weighted by mode mix if multi-mode).
    cell_length_m : float
        Physical length of one cell in metres (from config['grid']['cell_length_m']).

    Returns
    -------
    float
        Density in vehicles per kilometre.
    """
    if total_cells <= 0 or avg_vehicle_footprint_cells <= 0:
        return 0.0
    occupancy_ratio = occupied_cells / total_cells
    density_per_cell = occupancy_ratio / avg_vehicle_footprint_cells
    density_veh_per_km_val = density_per_cell * (1000.0 / cell_length_m)
    return float(density_veh_per_km_val)


def flow_veh_per_hr(crossings_in_window: int, window_s: int) -> float:
    """
    Convert crossing count to flow in veh/hr.

    Parameters
    ----------
    crossings_in_window : int
        Number of vehicles that crossed the measurement point in [window_start, window_end).
    window_s : int
        Width of the measurement window in seconds.

    Returns
    -------
    float
        Flow in vehicles per hour.
    """
    if window_s <= 0:
        return 0.0
    return float(crossings_in_window) * (3600.0 / window_s)


# ---------------------------------------------------------------------------
# Road geometry helper
# ---------------------------------------------------------------------------

def _avg_footprint(df_window: pd.DataFrame, mode_params: Optional[dict]) -> float:
    """
    Compute average vehicle footprint in cells for vehicles in df_window.
    Uses mode_params if provided (accurate); falls back to mean length_cells from df.
    """
    if mode_params is not None and "mode" in df_window.columns:
        lengths = df_window["mode"].map(
            lambda m: mode_params.get(m, {}).get("length_cells", 7)
        )
        if not lengths.empty:
            return float(lengths.mean())
    # Fallback — no mode info; use a generic car-length default
    return 7.0


# ---------------------------------------------------------------------------
# Primary Phase 6+ API
# ---------------------------------------------------------------------------

def flow_density_table(
    collector_df: pd.DataFrame,
    road_geometry: dict,
    window_s: int = 60,
    mode_params: Optional[dict] = None,
    measurement_point_offset: int = 50,
) -> pd.DataFrame:
    """
    Compute flow-density time-series from a Collector DataFrame.

    This is the single entry point for calibration (Phase 7) and validation (Phase 8).
    Produces one row per time window with:
      time_window, mode, density_veh_per_km, flow_veh_per_hr

    Parameters
    ----------
    collector_df : pd.DataFrame
        Output of Collector.to_dataframe().  Must contain at minimum:
        time_s, vehicle_id, position_cells, mode.
    road_geometry : dict
        Must contain:
          road_length_cells  : int
          cell_length_m      : float   (from config['grid']['cell_length_m'])
          road_width_cells   : int     (for 2D; used only for total_cells denominator)
    window_s : int
        Time-averaging window in seconds (default 60s = 1 minute).
    mode_params : dict or None
        config['mode_params'] dict — used for accurate per-mode footprint averages.
    measurement_point_offset : int
        Cells from end of road to place the crossing counter (default 50 cells = 25m).

    Returns
    -------
    pd.DataFrame
        Columns: time_window_start, time_window_end, mode, density_veh_per_km, flow_veh_per_hr
    """
    if collector_df is None or collector_df.empty:
        return pd.DataFrame(columns=[
            "time_window_start", "time_window_end", "mode",
            "density_veh_per_km", "flow_veh_per_hr",
        ])

    road_length_cells: int = road_geometry["road_length_cells"]
    cell_length_m: float = road_geometry["cell_length_m"]
    measurement_pt = road_length_cells - measurement_point_offset

    max_time = int(collector_df["time_s"].max())
    windows = list(range(0, max_time + 1, window_s))
    if len(windows) < 2:
        return pd.DataFrame(columns=[
            "time_window_start", "time_window_end", "mode",
            "density_veh_per_km", "flow_veh_per_hr",
        ])

    results = []
    modes = list(collector_df["mode"].unique()) if "mode" in collector_df.columns else ["all"]

    for i in range(len(windows) - 1):
        w_start = windows[i]
        w_end = windows[i + 1]
        mask = (collector_df["time_s"] >= w_start) & (collector_df["time_s"] < w_end)
        df_win = collector_df[mask]

        # --- Mixed traffic row ---
        if df_win.empty:
            results.append({
                "time_window_start": w_start, "time_window_end": w_end,
                "mode": "all",
                "density_veh_per_km": 0.0, "flow_veh_per_hr": 0.0,
            })
        else:
            # Occupied cells: sum of length_cells for each vehicle record,
            # averaged over the window (unique vehicles per timestep).
            occupied_per_t = []
            for ts, grp in df_win.groupby("time_s"):
                footprint = sum(
                    mode_params.get(row["mode"], {}).get("length_cells", 7)
                    if mode_params else 7
                    for _, row in grp.iterrows()
                )
                occupied_per_t.append(footprint)
            avg_occupied = np.mean(occupied_per_t) if occupied_per_t else 0.0
            total_cells = road_length_cells
            avg_fp = _avg_footprint(df_win, mode_params)
            dens = density_veh_per_km(int(avg_occupied), total_cells, avg_fp, cell_length_m)

            # Flow: vehicles crossing measurement point this window
            crossings = set()
            for vid, grp in df_win.groupby("vehicle_id"):
                prev_pos = grp["position_cells"].shift(1)
                crossed = grp[
                    (grp["position_cells"] >= measurement_pt) &
                    (prev_pos < measurement_pt)
                ]
                if not crossed.empty:
                    crossings.add(vid)
            fl = flow_veh_per_hr(len(crossings), w_end - w_start)

            results.append({
                "time_window_start": w_start, "time_window_end": w_end,
                "mode": "all",
                "density_veh_per_km": dens, "flow_veh_per_hr": fl,
            })

        # --- Per-mode rows ---
        if "mode" in collector_df.columns:
            for mode in modes:
                df_mode = df_win[df_win["mode"] == mode] if not df_win.empty else df_win
                if df_mode.empty:
                    results.append({
                        "time_window_start": w_start, "time_window_end": w_end,
                        "mode": mode,
                        "density_veh_per_km": 0.0, "flow_veh_per_hr": 0.0,
                    })
                    continue

                occupied_per_t = []
                mode_len = (mode_params or {}).get(mode, {}).get("length_cells", 7)
                for ts, grp in df_mode.groupby("time_s"):
                    occupied_per_t.append(len(grp) * mode_len)
                avg_occupied = np.mean(occupied_per_t) if occupied_per_t else 0.0
                avg_fp = float(mode_len)
                dens = density_veh_per_km(int(avg_occupied), road_length_cells, avg_fp, cell_length_m)

                crossings = set()
                for vid, grp in df_mode.groupby("vehicle_id"):
                    prev_pos = grp["position_cells"].shift(1)
                    crossed = grp[
                        (grp["position_cells"] >= measurement_pt) &
                        (prev_pos < measurement_pt)
                    ]
                    if not crossed.empty:
                        crossings.add(vid)
                fl = flow_veh_per_hr(len(crossings), w_end - w_start)

                results.append({
                    "time_window_start": w_start, "time_window_end": w_end,
                    "mode": mode,
                    "density_veh_per_km": dens, "flow_veh_per_hr": fl,
                })

    return pd.DataFrame(results)


def flow_density_by_mode_from_collector(
    collector_df: pd.DataFrame,
    road_geometry: dict,
    window_s: int = 60,
    mode_params: Optional[dict] = None,
    measurement_point_offset: int = 50,
) -> Dict[str, pd.DataFrame]:
    """
    Convenience wrapper that returns {mode: DataFrame} from a collector DataFrame.
    Compatible with Phase 1/2 plotting code that expects a dict keyed by mode.
    """
    big_df = flow_density_table(
        collector_df, road_geometry, window_s, mode_params, measurement_point_offset
    )
    if big_df.empty:
        return {}
    result = {}
    for mode, grp in big_df.groupby("mode"):
        result[mode] = grp.drop(columns=["mode"]).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# Legacy API (Phase 1/2 — kept for backward compatibility with regression tests)
# ---------------------------------------------------------------------------

def flow_density_from_log(
    df: pd.DataFrame,
    road_length_cells: int,
    cell_length_m: float,
    window_s: int,
    measurement_point_offset: int = 50,
) -> pd.DataFrame:
    """
    Legacy Phase 1/2 flow-density computation (kept for regression tests).
    density (veh/km) = avg number of vehicles on road / road length in km
    flow (veh/hr)    = vehicles crossing a fixed measurement point × (3600/window_s)
    """
    if df.empty:
        return pd.DataFrame(columns=["window_start", "window_end", "density_veh_per_km", "flow_veh_per_hr"])

    road_length_km = (road_length_cells * cell_length_m) / 1000.0
    measurement_point_cells = road_length_cells - measurement_point_offset

    max_time = df["time_s"].max()
    windows = list(range(0, int(max_time) + 1, window_s))

    results = []
    for i in range(len(windows) - 1):
        w_start = windows[i]
        w_end = windows[i + 1]
        mask = (df["time_s"] >= w_start) & (df["time_s"] < w_end)
        df_window = df[mask]

        if df_window.empty:
            density = 0.0
            fl = 0.0
        else:
            avg_vehicles = len(df_window) / float(window_s)
            density = avg_vehicles / road_length_km

            crossed_vehicles = set()
            for vid, group in df_window.groupby("vehicle_id"):
                crossings = group[
                    (group["position_cells"] >= measurement_point_cells) &
                    (group["position_cells"] - group["speed_cells_per_step"] < measurement_point_cells)
                ]
                if not crossings.empty:
                    crossed_vehicles.add(vid)
            fl = len(crossed_vehicles) * (3600.0 / window_s)

        results.append({
            "window_start": w_start,
            "window_end": w_end,
            "density_veh_per_km": density,
            "flow_veh_per_hr": fl,
        })

    return pd.DataFrame(results)


def flow_density_by_mode(
    df: pd.DataFrame,
    road_length_cells: int,
    cell_length_m: float,
    window_s: int,
    measurement_point_offset: int = 50,
) -> Dict[str, pd.DataFrame]:
    """
    Legacy Phase 2 per-mode flow-density computation (kept for regression tests).
    Returns a dict mapping mode name (and 'all') to its DataFrame of results.
    """
    out: Dict[str, pd.DataFrame] = {}
    out["all"] = flow_density_from_log(df, road_length_cells, cell_length_m, window_s, measurement_point_offset)

    if "mode" not in df.columns:
        return out

    for mode in df["mode"].unique():
        mode_df = df[df["mode"] == mode]
        out[mode] = flow_density_from_log(mode_df, road_length_cells, cell_length_m, window_s, measurement_point_offset)

    return out
