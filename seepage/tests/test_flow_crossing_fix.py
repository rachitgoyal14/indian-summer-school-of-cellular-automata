"""
Phase 6 prerequisite regression test: flow_density_table crossing fix.

Verifies that the global-prev_pos fix eliminates the window-boundary
crossing undercount that caused Phase 6's shift(1) method to miss ~1-3%
of crossings at capacity vs the Legacy method.

Per the bug report from Phase 6 investigation (script 24):
  Vehicle 801 at t=900, pos=1950, speed=30.
  Window: t=900-960.
  OLD Phase 6: shift(1) within window → NaN at t=900 → crossing MISSED.
  Legacy method: pos-speed = 1950-30 = 1920 < 1950 → crossing COUNTED.

After fix: global prev_pos at t=900 = pos at t=899 = 1920 → crossing COUNTED.

Acceptance criterion: at every window, flow from fixed Phase 6 method
equals flow from Legacy method to within ±1 vehicle (one vehicle rounding
at the boundary is acceptable; systematic multi-vehicle gaps are not).

The test also reproduces the specific vehicle-801 scenario to confirm
the fix catches that exact case.
"""
import pytest
import numpy as np
import pandas as pd

from src.core.config import load_config
from src.sim.sim_loop import run_midblock_simulation_multimode
from src.metrics.density_flow import (
    flow_density_table,
    flow_density_by_mode_from_collector,
    flow_density_by_mode,
    flow_veh_per_hr,
)

CONFIG_PATH = "configs/intersection_default.yaml"
RATE = 3500       # capacity-range rate where the bug was visible
DURATION = 600    # 10 minutes — enough for multiple windows
WINDOW_S = 60
SEED = 42


@pytest.fixture(scope="module")
def sim_df():
    config = load_config(CONFIG_PATH)
    rng = np.random.default_rng(SEED)
    return run_midblock_simulation_multimode(
        config, RATE, DURATION, {"two_wheeler": 1.0}, rng
    )


@pytest.fixture(scope="module")
def config():
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def road_geometry(config):
    cell_length_m = config["grid"]["cell_length_m"]
    road_length_cells = int(
        config["midblock_test"]["road_length_m"] / cell_length_m
    )
    return {"road_length_cells": road_length_cells, "cell_length_m": cell_length_m}


# ---------------------------------------------------------------------------
# 1. Fixed Phase 6 matches Legacy crossing counts (within ±1/window)
# ---------------------------------------------------------------------------

def test_flow_crossing_match_within_one_vehicle(sim_df, config, road_geometry):
    """
    Flow from fixed flow_density_table should match Legacy flow_density_by_mode
    within ±1 vehicle per window at all windows.

    ±1 is allowed because: the Legacy method uses 'pos - speed' to estimate
    prior position (may mis-assign fractional crossings at exact boundary);
    the fixed Phase 6 uses the actual prior position (more accurate).
    Systematic gaps >1 veh/window indicate the fix is incomplete.
    """
    cell_length_m = config["grid"]["cell_length_m"]
    road_length_cells = road_geometry["road_length_cells"]

    fd_p6 = flow_density_table(
        sim_df, road_geometry, window_s=WINDOW_S,
        mode_params=config["mode_params"]
    )
    fd_leg = flow_density_by_mode(
        sim_df, road_length_cells, cell_length_m, WINDOW_S
    )

    fd_p6_all = fd_p6[fd_p6["mode"] == "all"].copy()
    fd_leg_all = fd_leg.get("all", pd.DataFrame())

    assert not fd_p6_all.empty, "Phase 6 FD table is empty"
    assert not fd_leg_all.empty, "Legacy FD table is empty"

    # Convert flow back to crossing counts for comparison
    # flow_veh_per_hr = crossings * 3600 / window_s
    # → crossings = flow * window_s / 3600
    p6_crossings = (fd_p6_all["flow_veh_per_hr"] * WINDOW_S / 3600).round().astype(int)
    leg_crossings = (fd_leg_all["flow_veh_per_hr"] * WINDOW_S / 3600).round().astype(int)

    min_len = min(len(p6_crossings), len(leg_crossings))
    p6_arr = p6_crossings.values[:min_len]
    leg_arr = leg_crossings.values[:min_len]

    diffs = p6_arr - leg_arr
    bad_windows = np.where(np.abs(diffs) > 1)[0]

    assert len(bad_windows) == 0, (
        f"Flow crossing counts differ by >1 vehicle in {len(bad_windows)} windows:\n"
        + "\n".join(
            f"  window {i}: P6={p6_arr[i]}, Legacy={leg_arr[i]}, diff={diffs[i]}"
            for i in bad_windows[:10]
        )
    )


# ---------------------------------------------------------------------------
# 2. Global prev_pos fix captures the specific vehicle-801 scenario
# ---------------------------------------------------------------------------

def test_boundary_crossing_captured_by_global_prev_pos(sim_df, road_geometry, config):
    """
    Construct a minimal scenario where a vehicle is exactly at the
    measurement point at the FIRST timestep of a window (the case that
    broke the old shift(1)-within-window approach), and confirm the
    fixed method counts it as a crossing.
    """
    road_length_cells = road_geometry["road_length_cells"]
    cell_length_m = road_geometry["cell_length_m"]
    meas_pt = road_length_cells - 50

    # Build a synthetic 2-row DataFrame:
    #   t=59 (outside window 60-120): pos = meas_pt - 1 (just behind)
    #   t=60 (first row of window):   pos = meas_pt     (exactly at point)
    # Only the t=60 row falls in the window [60, 120).
    # OLD shift(1): prev_pos at t=60 = NaN → not counted.
    # FIXED:        prev_pos at t=60 = meas_pt-1 → counted correctly.
    synthetic = pd.DataFrame([
        {"time_s": 59, "vehicle_id": 9999, "mode": "two_wheeler",
         "position_cells": meas_pt - 1, "lateral_position_cells": 0,
         "speed_cells_per_step": 1, "leg_origin": 0, "leg_destination": None,
         "turn": None, "accel_cells_per_step2": None, "accel_artifact_seepage": False,
         "in_izoi": False, "signal_state": None, "seepage_action": None},
        {"time_s": 60, "vehicle_id": 9999, "mode": "two_wheeler",
         "position_cells": meas_pt, "lateral_position_cells": 0,
         "speed_cells_per_step": 1, "leg_origin": 0, "leg_destination": None,
         "turn": None, "accel_cells_per_step2": 0, "accel_artifact_seepage": False,
         "in_izoi": False, "signal_state": None, "seepage_action": None},
        {"time_s": 61, "vehicle_id": 9999, "mode": "two_wheeler",
         "position_cells": meas_pt + 1, "lateral_position_cells": 0,
         "speed_cells_per_step": 1, "leg_origin": 0, "leg_destination": None,
         "turn": None, "accel_cells_per_step2": 0, "accel_artifact_seepage": False,
         "in_izoi": False, "signal_state": None, "seepage_action": None},
        # Padding row at t=121 so flow_density_table generates window [60,120).
        # max_time must be >= 120 for windows = [0, 60, 120].
        {"time_s": 121, "vehicle_id": 9999, "mode": "two_wheeler",
         "position_cells": meas_pt + 60, "lateral_position_cells": 0,
         "speed_cells_per_step": 1, "leg_origin": 0, "leg_destination": None,
         "turn": None, "accel_cells_per_step2": 0, "accel_artifact_seepage": False,
         "in_izoi": False, "signal_state": None, "seepage_action": None},
    ])

    fd = flow_density_table(
        synthetic, road_geometry, window_s=60,
        mode_params=config["mode_params"]
    )
    window_60_all = fd[(fd["time_window_start"] == 60) & (fd["mode"] == "all")]

    assert not window_60_all.empty, "No row for window 60-120 in fixed FD table"
    flow_val = window_60_all["flow_veh_per_hr"].iloc[0]
    # 1 vehicle crossing in 60s window → 60 veh/hr
    assert flow_val == pytest.approx(60.0, abs=1.0), (
        f"Window-boundary crossing not counted: flow={flow_val} (expected 60 veh/hr). "
        "The global prev_pos fix is not working."
    )


# ---------------------------------------------------------------------------
# 3. Phase 6 total crossings >= Legacy (fixed should never UNDER-count)
# ---------------------------------------------------------------------------

def test_fixed_p6_not_below_legacy(sim_df, road_geometry, config):
    """
    After the fix, Phase 6 flow should be >= Legacy flow at every window
    (Phase 6 uses actual prior position; Legacy uses pos-speed approximation
    which can also miss crossings when speed is underestimated).
    Allow Legacy to exceed P6 by at most 1 vehicle/window (rounding).
    """
    cell_length_m = config["grid"]["cell_length_m"]
    road_length_cells = road_geometry["road_length_cells"]

    fd_p6 = flow_density_table(sim_df, road_geometry, window_s=WINDOW_S,
                               mode_params=config["mode_params"])
    fd_leg = flow_density_by_mode(sim_df, road_length_cells, cell_length_m, WINDOW_S)

    fd_p6_all = fd_p6[fd_p6["mode"] == "all"]
    fd_leg_all = fd_leg.get("all", pd.DataFrame())

    min_len = min(len(fd_p6_all), len(fd_leg_all))
    p6_flows = fd_p6_all["flow_veh_per_hr"].values[:min_len]
    leg_flows = fd_leg_all["flow_veh_per_hr"].values[:min_len]

    # Compute crossings (integer counts)
    p6_c = (p6_flows * WINDOW_S / 3600).round().astype(int)
    leg_c = (leg_flows * WINDOW_S / 3600).round().astype(int)

    # Phase 6 should not miss crossings that Legacy catches (>1 gap)
    undercount = leg_c - p6_c
    bad = np.where(undercount > 1)[0]
    assert len(bad) == 0, (
        f"Fixed P6 undercounts Legacy by >1 vehicle in {len(bad)} windows: "
        f"{[(i, int(undercount[i])) for i in bad[:5]]}"
    )


# ---------------------------------------------------------------------------
# 4. EXACT MATCH — no-boundary-vehicle scenario (algebraic equivalence test)
#    When no vehicle straddles a window boundary (i.e., all vehicles' prior
#    positions are recorded within the same window), both methods must agree
#    to the exact integer crossing count — not just within ±1.
#    This is the "algebraic equivalence" analogue for flow counting,
#    as requested in the Phase 7 prerequisite spec.
# ---------------------------------------------------------------------------

def test_exact_crossing_count_no_boundary_vehicle(road_geometry, config):
    """
    Synthetic scenario: one vehicle crosses the measurement point at t=30
    (mid-window in [0,60)), with its prior position at t=29 also within the
    window.  Neither method needs cross-window data, so both must count
    exactly 1 crossing — exact integer agreement, not just ±1.

    This proves the fix did not introduce spurious crossings or miss any
    for the nominal (non-boundary) case.
    """
    road_length_cells = road_geometry["road_length_cells"]
    cell_length_m = road_geometry["cell_length_m"]
    meas_pt = road_length_cells - 50

    # Vehicle travels at speed=1: at t=29 it is at meas_pt-1, at t=30 at meas_pt.
    # All rows are in window [0,60) — no boundary crossing needed.
    rows = []
    for t in range(10, 60):
        pos = meas_pt - (30 - t) if t <= 30 else meas_pt + (t - 30)
        rows.append({
            "time_s": t, "vehicle_id": 7777, "mode": "two_wheeler",
            "position_cells": pos, "lateral_position_cells": 0,
            "speed_cells_per_step": 1,
            "leg_origin": 0, "leg_destination": None, "turn": None,
            "accel_cells_per_step2": 0, "accel_artifact_seepage": False,
            "in_izoi": False, "signal_state": None, "seepage_action": None,
        })
    # Padding row so flow_density_table generates windows [0,60) and [60,120).
    rows.append({
        "time_s": 61, "vehicle_id": 7777, "mode": "two_wheeler",
        "position_cells": meas_pt + 32, "lateral_position_cells": 0,
        "speed_cells_per_step": 1,
        "leg_origin": 0, "leg_destination": None, "turn": None,
        "accel_cells_per_step2": 0, "accel_artifact_seepage": False,
        "in_izoi": False, "signal_state": None, "seepage_action": None,
    })

    synthetic = pd.DataFrame(rows)
    road_geom = road_geometry

    # Phase 6 fixed method
    fd_p6 = flow_density_table(
        synthetic, road_geom, window_s=60,
        mode_params=config["mode_params"]
    )
    p6_w0 = fd_p6[(fd_p6["time_window_start"] == 0) & (fd_p6["mode"] == "all")]
    assert not p6_w0.empty, "No row for window [0,60) in P6 FD table"

    # Legacy method
    from src.metrics.density_flow import flow_density_by_mode
    fd_leg = flow_density_by_mode(synthetic, road_length_cells, cell_length_m, 60)
    leg_w0 = fd_leg["all"][fd_leg["all"]["window_start"] == 0]
    assert not leg_w0.empty, "No row for window [0,60) in Legacy FD table"

    p6_flow  = float(p6_w0["flow_veh_per_hr"].iloc[0])
    leg_flow = float(leg_w0["flow_veh_per_hr"].iloc[0])

    # Expected: 1 crossing × 3600/60 = 60 veh/hr
    expected = 60.0
    assert p6_flow == pytest.approx(expected, abs=1e-9), (
        f"P6 fixed method counted wrong crossings: flow={p6_flow} (expected {expected})"
    )
    assert leg_flow == pytest.approx(expected, abs=1e-9), (
        f"Legacy method counted wrong crossings: flow={leg_flow} (expected {expected})"
    )
    # EXACT integer agreement (the algebraic equivalence requirement):
    p6_count  = round(p6_flow  * 60 / 3600)
    leg_count = round(leg_flow * 60 / 3600)
    assert p6_count == leg_count == 1, (
        f"Exact-match failed: P6 count={p6_count}, Legacy count={leg_count} "
        f"(expected both = 1, flows: P6={p6_flow}, Legacy={leg_flow})"
    )
