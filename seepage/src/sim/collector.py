"""
Phase 6 — Canonical data collector.

Collector class with:
  .record(t_s, vehicles, extra_fields) — called once per simulation timestep
  .to_dataframe()                       — returns pd.DataFrame with full canonical schema

Canonical column set (per phase06_data_collection.md spec):
    time_s, vehicle_id, mode, leg_origin, leg_destination, turn,
    position_cells, lateral_position_cells, speed_cells_per_step,
    accel_cells_per_step2, in_izoi, signal_state, seepage_action

accel_cells_per_step2 is computed internally by diffing consecutive speed records
per vehicle — sim_loop.py does NOT need to track this separately.

Phase 5 seepage-speed artifact (flagged in PHASE_REPORT.md):
After a seep move, speed_cells_per_step is restored to the advance distance (2 or 1
cells/step) rather than 0.  At the NEXT timestep accelerate() may increment this to 3+
cells/step, producing an apparent acceleration of (new_speed - advance) cells/step² —
up to ~28 cells/step² for a two-wheeler — which is a logging artifact, not a real
kinematic event.

Approach taken: MASK (flag) these rows rather than silently recompute from position
diffs, so Phase 8 validation consumers can exclude them explicitly.
Concretely: if `seepage_action` for a vehicle at t-1 was one of
{"seep_left","seep_right","seep_diagonal"}, the accel value at time t is flagged
as NaN (artifact masked), and a companion boolean column
`accel_artifact_seepage` is set True for that row.

This preserves the full data while giving downstream consumers an unambiguous mask
to filter before computing acceleration statistics.
"""

from __future__ import annotations

import pandas as pd
from typing import List, Optional

from src.core.vehicle import Vehicle


class Collector:
    """
    Canonical per-timestep data collector for all simulation phases.

    Parameters
    ----------
    izoi_distances_cells : dict[str, int]
        Per-mode IZOI distance in cells, keyed by mode string.
        Used to compute the `in_izoi` boolean column.
    stop_line_cells : int | None
        Longitudinal position of the stop line (for multi-leg intersections,
        pass None and set the per-leg stop line in `extra_fields`).
    """

    # Seep actions that produce the speed artifact at the NEXT timestep
    _SEEP_ACTIONS = frozenset({"seep_left", "seep_right", "seep_diagonal"})

    def __init__(
        self,
        izoi_distances_cells: Optional[dict] = None,
        stop_line_cells: Optional[int] = None,
    ) -> None:
        self._izoi_distances_cells = izoi_distances_cells or {}
        self._stop_line_cells = stop_line_cells

        # Internal state: last seen speed per vehicle (for accel diff)
        self._last_speed: dict[int, int] = {}
        # Internal state: seepage action at previous timestep per vehicle
        self._last_seep_action: dict[int, Optional[str]] = {}

        self._rows: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        t_s: int,
        vehicles: List[Vehicle],
        extra_fields: Optional[dict] = None,
    ) -> None:
        """
        Record one timestep.

        Parameters
        ----------
        t_s : int
            Current simulation time in seconds.
        vehicles : list[Vehicle]
            All active vehicles this timestep.
        extra_fields : dict or None
            Additional per-call fields merged into every row.  Used by sim_loop
            to pass leg-level context (signal_state, seepage_action dict, etc.)
            without coupling Vehicle to intersection concepts.

            Recognized keys (all optional):
              signal_state    : str  — "red" | "green"
              seepage_actions : dict[int, str|None] — vehicle_id → seepage_action
              leg_origin      : int  — leg this batch of vehicles came from
              leg_destination : int  — (future) destination leg
              turns           : dict[int, str] — vehicle_id → turn direction
              stop_line_cells : int  — override per-leg stop line
        """
        if extra_fields is None:
            extra_fields = {}

        signal_state = extra_fields.get("signal_state", None)
        seepage_actions: dict[int, Optional[str]] = extra_fields.get("seepage_actions", {})
        leg_origin = extra_fields.get("leg_origin", None)
        leg_destination = extra_fields.get("leg_destination", None)
        turns: dict[int, str] = extra_fields.get("turns", {})
        stop_line_cells = extra_fields.get("stop_line_cells", self._stop_line_cells)

        for v in vehicles:
            speed_now = int(v.speed_cells_per_step)
            prev_speed = self._last_speed.get(v.id, None)
            prev_seep = self._last_seep_action.get(v.id, None)

            # Acceleration computation with seepage-artifact masking
            if prev_speed is None:
                # First timestep for this vehicle — no previous speed
                accel = None
                accel_artifact = False
            elif prev_seep in self._SEEP_ACTIONS:
                # Speed at t-1 was artificially set to advance distance (≤2 cells/step).
                # The diff (speed_now - advance) is NOT a real acceleration.
                accel = float("nan")
                accel_artifact = True
            else:
                accel = speed_now - prev_speed
                accel_artifact = False

            # IZOI membership
            in_izoi = False
            if stop_line_cells is not None and v.mode in self._izoi_distances_cells:
                izoi_dist = self._izoi_distances_cells[v.mode]
                dist_to_stop = stop_line_cells - v.position_cells
                in_izoi = 0 <= dist_to_stop <= izoi_dist

            seep_action = seepage_actions.get(v.id, None)

            row = {
                "time_s": t_s,
                "vehicle_id": v.id,
                "mode": v.mode,
                "leg_origin": leg_origin,
                "leg_destination": leg_destination,
                "turn": turns.get(v.id, None),
                "position_cells": v.position_cells,
                "lateral_position_cells": v.lateral_position_cells,
                "speed_cells_per_step": speed_now,
                "accel_cells_per_step2": accel,
                "accel_artifact_seepage": accel_artifact,
                "in_izoi": in_izoi,
                "signal_state": signal_state,
                "seepage_action": seep_action,
            }
            self._rows.append(row)

            # Update internal state for next timestep
            self._last_speed[v.id] = speed_now
            self._last_seep_action[v.id] = seep_action

    def to_dataframe(self) -> pd.DataFrame:
        """Return all logged records as a canonical DataFrame."""
        if not self._rows:
            return pd.DataFrame(columns=[
                "time_s", "vehicle_id", "mode", "leg_origin", "leg_destination",
                "turn", "position_cells", "lateral_position_cells",
                "speed_cells_per_step", "accel_cells_per_step2",
                "accel_artifact_seepage", "in_izoi", "signal_state", "seepage_action",
            ])
        df = pd.DataFrame(self._rows)
        # Ensure canonical column order
        cols = [
            "time_s", "vehicle_id", "mode", "leg_origin", "leg_destination",
            "turn", "position_cells", "lateral_position_cells",
            "speed_cells_per_step", "accel_cells_per_step2",
            "accel_artifact_seepage", "in_izoi", "signal_state", "seepage_action",
        ]
        # Add any missing cols (safety — should not happen)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        return df[cols].reset_index(drop=True)

    def reset(self) -> None:
        """Clear all records and internal state (useful for restartable runs)."""
        self._rows.clear()
        self._last_speed.clear()
        self._last_seep_action.clear()
