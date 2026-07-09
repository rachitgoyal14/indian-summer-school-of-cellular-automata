"""
Phase 6 — Trajectory export.

Converts collector DataFrame from cell-space to physical-space (metres)
and writes a minimal trajectory CSV that matches the field-data schema
from Phase 0, so Phase 8 validation can compare field vs. simulated
trajectories using the exact same loading code.

Output schema (matching Kanagaraj dataset canonical columns):
    vehicle_id, mode, time_s, x_m, y_m, speed_mps

Where:
  x_m       = position_cells × cell_length_m   (longitudinal, m)
  y_m       = lateral_position_cells × cell_width_m  (lateral, m)
  speed_mps = speed_cells_per_step × cell_length_m   (m/s, since 1 step = 1 second)
"""

from __future__ import annotations

import os
import pandas as pd


def export_trajectories(
    collector_df: pd.DataFrame,
    out_path: str,
    cell_length_m: float,
    cell_width_m: float,
) -> None:
    """
    Write a clean trajectory CSV from a Collector DataFrame.

    Parameters
    ----------
    collector_df : pd.DataFrame
        Output of Collector.to_dataframe().
    out_path : str
        Absolute path to write the CSV file.
        Parent directories are created if they do not exist.
    cell_length_m : float
        Physical length of one longitudinal cell in metres
        (from config['grid']['cell_length_m']).
    cell_width_m : float
        Physical width of one lateral cell in metres
        (from config['grid']['cell_width_m']).
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Convert to physical coordinates
    traj = pd.DataFrame({
        "vehicle_id":   collector_df["vehicle_id"],
        "mode":         collector_df["mode"],
        "time_s":       collector_df["time_s"],
        "x_m":          collector_df["position_cells"] * cell_length_m,
        "y_m":          collector_df["lateral_position_cells"] * cell_width_m,
        "speed_mps":    collector_df["speed_cells_per_step"] * cell_length_m,
    })

    traj = traj.sort_values(["vehicle_id", "time_s"]).reset_index(drop=True)
    traj.to_csv(out_path, index=False)
    print(f"[trajectory_export] Written {len(traj)} rows to {out_path}")
