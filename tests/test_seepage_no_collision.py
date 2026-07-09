"""
Phase 5 — Seepage collision test.

Tests that zero cell-occupancy collisions occur in a seepage-heavy scenario
(high two-wheeler proportion, 5+ signal cycles) even with seepage moves active.

Per the Phase 4 lessons-learned, extended/stressed runs are specifically needed
to surface collision bugs — this test runs for 10 full signal cycles (1300s).
"""

import pytest
import numpy as np
from src.core.config import load_config
from src.sim.sim_loop import run_single_leg_with_seepage


def _detect_collisions(df, mode_params: dict) -> list[tuple]:
    """
    Check for cell-occupancy collisions at every timestep.
    
    A collision is detected when two vehicles occupy the same (position, lateral)
    cell at the same time, accounting for each vehicle's full footprint.
    
    Returns a list of (t, vid1, vid2, cell) collision records.
    """
    collisions = []
    for t, grp in df.groupby('time_s'):
        occupancy = {}  # (pos_cell, lat_cell) -> vehicle_id
        for _, row in grp.iterrows():
            vid = row['vehicle_id']
            mode = row['mode']
            length = mode_params[mode]['length_cells']
            width = mode_params[mode]['width_cells']
            front = int(row['position_cells'])
            lat   = int(row['lateral_position_cells'])
            
            for x in range(front - length + 1, front + 1):
                for y in range(lat, lat + width):
                    cell = (x, y)
                    if cell in occupancy:
                        collisions.append((t, occupancy[cell], vid, cell))
                    else:
                        occupancy[cell] = vid
    return collisions


def test_seepage_heavy_no_collision():
    """
    High two-wheeler proportion (70%) scenario with seepage ON.
    Run 10 full signal cycles (130s × 10 = 1300s).
    Assert ZERO cell-occupancy collisions.
    
    This tests the specific scenario most likely to surface seepage collision bugs:
    - Many two-wheelers (70%) aggressively seeping
    - 5 full signal cycles (per acceptance criterion: "at least 5+ signal cycles")
    - We run 10 cycles for extra safety margin given Phase 4 lessons
    """
    config = load_config("configs/intersection_default.yaml")
    
    # High two-wheeler proportion — seepage-heavy scenario
    mode_mix = {
        'two_wheeler': 0.70,
        'car': 0.15,
        'three_wheeler': 0.12,
        'bus': 0.03,
    }
    
    rate_veh_per_hour = 800  # Sub-capacity demand so queue clears each cycle
    duration_s = 1300  # 10 full signal cycles (130s × 10)
    
    rng = np.random.default_rng(777)
    
    # Run with seepage ENABLED (uses config defaults: two_wheeler and three_wheeler eligible)
    df = run_single_leg_with_seepage(
        config, rate_veh_per_hour, duration_s, mode_mix, rng,
        seepage_eligible_modes_override=None,  # Use config default
    )
    
    assert len(df) > 0, "Simulation produced no records"
    
    collisions = _detect_collisions(df, config['mode_params'])
    
    if collisions:
        # Report first 5 collisions for debugging
        for t, v1, v2, cell in collisions[:5]:
            print(f"  Collision at t={t}: vehicle {v1} and {v2} at cell {cell}")
    
    assert len(collisions) == 0, (
        f"Found {len(collisions)} cell-occupancy collisions in seepage-heavy "
        f"scenario. First collision: t={collisions[0][0]}, "
        f"vehicles={collisions[0][1]},{collisions[0][2]}, cell={collisions[0][3]}"
    )


def test_seepage_off_no_collision_baseline():
    """
    Regression: seepage OFF must also have zero collisions.
    Confirms the baseline behavior is unchanged.
    """
    config = load_config("configs/intersection_default.yaml")
    
    mode_mix = {
        'two_wheeler': 0.546,
        'car': 0.267,
        'three_wheeler': 0.151,
        'bus': 0.036,
    }
    
    duration_s = 650  # 5 full signal cycles
    rng = np.random.default_rng(888)
    
    df = run_single_leg_with_seepage(
        config, 800, duration_s, mode_mix, rng,
        seepage_eligible_modes_override=[],  # seepage OFF
    )
    
    collisions = _detect_collisions(df, config['mode_params'])
    assert len(collisions) == 0, f"Found {len(collisions)} collisions with seepage OFF"


def test_seepage_action_column_present():
    """
    Verify the seepage_action column is present in the output DataFrame
    and contains only valid values.
    """
    config = load_config("configs/intersection_default.yaml")
    mode_mix = {
        'two_wheeler': 0.546, 'car': 0.267,
        'three_wheeler': 0.151, 'bus': 0.036,
    }
    rng = np.random.default_rng(123)
    df = run_single_leg_with_seepage(config, 800, 260, mode_mix, rng)
    
    assert 'seepage_action' in df.columns, "seepage_action column missing from output"
    
    valid_actions = {None, 'seep_left', 'seep_right', 'seep_diagonal', 'stopped', float('nan')}
    unique_actions = set(df['seepage_action'].unique())
    
    # Check all non-None values are valid action strings
    invalid = {a for a in unique_actions if a is not None and not isinstance(a, float) and a not in ('seep_left', 'seep_right', 'seep_diagonal', 'stopped')}
    assert len(invalid) == 0, f"Invalid seepage_action values found: {invalid}"


def test_seepage_vehicles_dont_cross_stop_line():
    """
    Seeping vehicles must never advance past the stop line.
    Per implementation: position_cells <= stop_line_position_cells - 1.
    """
    config = load_config("configs/intersection_default.yaml")
    mode_mix = {
        'two_wheeler': 0.70, 'car': 0.10,
        'three_wheeler': 0.17, 'bus': 0.03,
    }
    rng = np.random.default_rng(456)
    df = run_single_leg_with_seepage(config, 800, 260, mode_mix, rng)
    
    road_length_cells = int(
        config['midblock_test']['road_length_m'] / config['grid']['cell_length_m']
    )
    stop_line_cells = road_length_cells - 100
    
    # Seeping vehicles should never cross the stop line
    seeping = df[df['seepage_action'].isin(['seep_left', 'seep_right', 'seep_diagonal'])]
    violations = seeping[seeping['position_cells'] >= stop_line_cells]
    
    assert len(violations) == 0, (
        f"Found {len(violations)} seeping vehicles past the stop line. "
        f"Max position seen: {seeping['position_cells'].max()} vs stop at {stop_line_cells}"
    )
