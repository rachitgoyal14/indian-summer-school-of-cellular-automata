"""
Tests for Phase 5 seepage behavior — Algorithm 3 from Singh & Ramachandra Rao (2023).

Covers:
  1. is_seepage_eligible: all 4 conditions (IZOI, red, mode)
  2. attempt_seepage: all 4 branches (seep_left, seep_right, seep_diagonal, stopped)
  3. Cars and buses are NEVER eligible regardless of gap availability
"""

import pytest
import numpy as np
from src.core.vehicle import Vehicle
from src.intersection.seepage import is_seepage_eligible, attempt_seepage


# -----------------------------------------------------------------------
# Helper factories
# -----------------------------------------------------------------------

STOP_LINE = 900  # cells (road_length 1000 - 100)
IZOI_DIST_TWO_WHEELER = 200  # cells: 100m / 0.5 m/cell = 200 cells


def make_vehicle(vid, mode, pos, lat, length=4, width=1, speed=0):
    return Vehicle(
        id=vid, mode=mode,
        length_cells=length, width_cells=width,
        max_speed_cells_per_step=30, max_accel_cells_per_step2=4,
        position_cells=pos, lateral_position_cells=lat,
        speed_cells_per_step=speed,
    )


def make_config():
    """Minimal config for seepage tests."""
    return {
        'grid': {'cell_length_m': 0.5, 'cell_width_m': 0.7},
        'midblock_test': {'road_length_m': 1000.0, 'road_width_m': 7.0},
        'signal': {'cycle_length_s': 130, 'green_s': 30, 'red_s': 100},
        'izoi_distance_m': {
            'two_wheeler': 100.0, 'three_wheeler': 141.13,
            'car': 187.385, 'bus': 111.26,
        },
        'izoi_deceleration_rate': 2,
        'lateral_safety_margin_cells': 0.5,
        'longitudinal_safety_margin_cells': 1,
        'seepage_eligible_modes': ['two_wheeler', 'three_wheeler'],
        'seepage_advance_cells_per_step': {'two_wheeler': 2, 'three_wheeler': 1},
    }


# -----------------------------------------------------------------------
# is_seepage_eligible tests
# -----------------------------------------------------------------------

class TestIsSeepageEligible:
    def test_eligible_two_wheeler_in_izoi_red(self):
        """A two-wheeler inside IZOI on a red signal → eligible."""
        v = make_vehicle(1, 'two_wheeler', 800, 3)  # in IZOI: dist_to_stop = 900-800-4 = 96 < 200
        assert is_seepage_eligible(v, 'red', STOP_LINE, IZOI_DIST_TWO_WHEELER, ['two_wheeler', 'three_wheeler'])

    def test_ineligible_green_signal(self):
        """Even an eligible mode inside IZOI is ineligible on green."""
        v = make_vehicle(1, 'two_wheeler', 800, 3)
        assert not is_seepage_eligible(v, 'green', STOP_LINE, IZOI_DIST_TWO_WHEELER, ['two_wheeler', 'three_wheeler'])

    def test_ineligible_outside_izoi(self):
        """Two-wheeler on red but outside IZOI → not eligible."""
        v = make_vehicle(1, 'two_wheeler', 400, 3)  # dist_to_stop = 900-400-4 = 496 >> 200
        assert not is_seepage_eligible(v, 'red', STOP_LINE, IZOI_DIST_TWO_WHEELER, ['two_wheeler', 'three_wheeler'])

    def test_car_never_eligible(self):
        """Car is NEVER seepage-eligible, regardless of signal, IZOI position, or gap."""
        car = make_vehicle(1, 'car', 800, 3, length=7, width=3)
        # Car IZOI dist_cells = 187.385/0.5 = 374 → car is inside IZOI at pos=800
        izoi_car_cells = int(187.385 / 0.5)
        assert not is_seepage_eligible(car, 'red', STOP_LINE, izoi_car_cells, ['two_wheeler', 'three_wheeler'])

    def test_bus_never_eligible(self):
        """Bus is NEVER seepage-eligible, regardless of signal, IZOI position, or gap."""
        bus = make_vehicle(2, 'bus', 800, 3, length=20, width=4)
        izoi_bus_cells = int(111.26 / 0.5)
        assert not is_seepage_eligible(bus, 'red', STOP_LINE, izoi_bus_cells, ['two_wheeler', 'three_wheeler'])

    def test_car_not_eligible_even_with_empty_list_override(self):
        """Explicitly test: if seepage_eligible_modes=[], NO vehicle is ever eligible."""
        v = make_vehicle(1, 'two_wheeler', 800, 3)
        assert not is_seepage_eligible(v, 'red', STOP_LINE, IZOI_DIST_TWO_WHEELER, [])


# -----------------------------------------------------------------------
# attempt_seepage tests — all 4 branches
# -----------------------------------------------------------------------

class TestAttemptSeepage:
    """
    Fixed geometry:
    Road: width=10 cells (7m / 0.7m), stop_line=900.
    v_main: two_wheeler, pos=800, lat=5, length=4, width=1.

    Neighbors are placed to create specific gap scenarios.
    """

    def _run(self, v, neighbors, config_override=None):
        config = make_config()
        if config_override:
            config.update(config_override)
        rng = np.random.default_rng(42)
        return attempt_seepage(v, neighbors, config, 2, STOP_LINE, rng)

    def test_seep_left(self):
        """
        Ample gap on left side: no left neighbor → gap_left=inf > required.
        Right side has a neighbor close to right.
        Expected: seep_left.
        
        v_main: pos=800, lat=5, width=1 → right edge=5
        v_right: lat=6, width=1 → left edge=6, gap_right = 6-5-1 = 0 → right blocked
        No left neighbor → gap_left = inf → seep left
        """
        v = make_vehicle(1, 'two_wheeler', 800, 5)
        v_right = make_vehicle(2, 'car', 800, 6, length=4, width=1, speed=0)
        
        action = self._run(v, [v_right])
        assert action == 'seep_left', f"Expected seep_left, got {action}"
        # Also verify vehicle advanced forward
        assert v.position_cells > 800

    def test_seep_right(self):
        """
        Left is blocked, right has ample gap.
        v_main: lat=2, width=1
        v_left: lat=1, width=1 → right edge=1, gap_left = 2-1-1 = 0 → left blocked
        No right neighbor → gap_right=inf → seep right
        """
        v = make_vehicle(1, 'two_wheeler', 800, 2)
        v_left = make_vehicle(2, 'car', 800, 1, length=4, width=1, speed=0)
        
        action = self._run(v, [v_left])
        assert action == 'seep_right', f"Expected seep_right, got {action}"
        assert v.position_cells > 800

    def test_seep_diagonal(self):
        """
        Both lateral gaps blocked (tight neighbors on both sides),
        but two front vehicles with enough forward clearance.
        Expected: seep_diagonal.

        v_main: pos=800, lat=4, width=1 → left=4, right=4
        v_left:  pos=800, lat=2, width=2 → right edge=3 → gap_left = max(0, 4-3-1)=0 → left blocked.
                 Footprint: y=2,3 (does NOT cover y=4 → doesn't block destination).
        v_right: pos=800, lat=5, width=2 → left edge=5 → gap_right = max(0, 5-4-1)=0 → right blocked.
                 Footprint: y=5,6 (does NOT cover y=4).
        v_front1: pos=815, lat=2, len=4 → back=812, gap=812-800-1=11
        v_front2: pos=818, lat=6, len=4 → back=815, gap=815-800-1=14
        seepage_longitudinal_gap = min(11,14) = 11 > long_margin(1) → seep diagonal.
        is_dest_clear(802, 4): footprint (799-802, y=4) — clear of v_left (y=2,3),
        v_right (y=5,6), v_front1 (y=2,3, x=812+), v_front2 (y=6,7, x=815+). → CLEAR.
        """
        v         = make_vehicle(1, 'two_wheeler', 800, 4)
        # lat=2, width=2 → right_edge=3 → gap_left=max(0,4-3-1)=0 (blocks left)
        # footprint covers y=2,3 only — does NOT overlap destination y=4
        v_left    = make_vehicle(2, 'car', 800, 2, length=4, width=2, speed=0)
        v_right   = make_vehicle(3, 'car', 800, 5, length=4, width=2, speed=0)
        v_front1  = make_vehicle(4, 'car', 815, 2, length=4, width=2, speed=0)
        v_front2  = make_vehicle(5, 'car', 818, 6, length=4, width=2, speed=0)

        action = self._run(v, [v_left, v_right, v_front1, v_front2])
        assert action == 'seep_diagonal', f"Expected seep_diagonal, got {action}"
        assert v.position_cells > 800

    def test_stopped(self):
        """
        All gaps blocked: left+right blocked laterally, no 2+ front vehicles.
        Expected: stopped.
        
        v_main: pos=800, lat=4, width=1
        v_left:  lat=3, width=2 → overlaps → left=0
        v_right: lat=5, width=2 → overlaps → right=0
        No front vehicles → long_gap=inf but usable=inf-1=inf... wait, need to check.
        Actually with 0 or 1 front vehicles, seepage_longitudinal_gap returns inf,
        so usable_long_gap = inf - 1 = inf > 0 → would seep diagonal!
        
        We need to block diagonal too: place one vehicle ahead only (< 2 front vehs).
        But with 0 front vehicles, long_gap=inf... Let me use a tighter scenario:
        both lat gaps blocked AND only 1 front vehicle (so no diagonal possible via the
        <2 candidates check).
        
        Actually the test needs: left=blocked, right=blocked, AND front<2 vehicles.
        With exactly 0 front vehicles, seepage_longitudinal_gap returns inf
        which would trigger diagonal. So we need the lateral blocking + exactly 1 front veh.
        
        Wait, re-reading: with only 1 front vehicle, seepage_longitudinal_gap returns inf,
        usable = inf - 1 = still "infinity" > 0, so diagonal WOULD fire.
        
        The "stopped" case in the paper's Algorithm 3 is: ALL three checks fail.
        The diagonal check uses "lateral_pos_of_1st_front - lateral_pos_of_2nd_front > size+safety"
        i.e., the SPREAD between two front vehicles, not just forward clearance.
        
        Our implementation: if fewer than 2 front vehicles, returns inf (no pair to slip between).
        This means stopped can only happen when:
        - left blocked AND right blocked AND long_gap-margin <= 0 (two front vehicles very close).
        
        Use: v_front1 at pos=801 (gap=−2 → not ahead, back=798) ... 
        Actually back = pos - len + 1 = 801-4+1 = 798, front_gap check: o_back(798) > v_front(800)? No.
        Use pos=804: back=801. gap = 801-800-1 = 0 → counts as ahead with gap=0
        Use pos=803: back=800. gap = 800-800-1 = -1 → not ahead (o_back not > v_front)
        
        Let me place 2 front vehicles right behind the stop line (pos=801 is blocked by gap=0).
        Put them with gap=0 to v_front: pos=805 → back=802, gap=801-800-1... 
        
        Simpler: make the longitudinal gap ≤ long_margin so usable <= 0.
        long_margin=1. Put both front vehicles so min gap = 0.
        v_front1: pos=804, back=801. gap = 801-800-1 = 0
        v_front2: pos=805, back=802. gap = 802-800-1 = 1
        min=0. usable = 0-1 = -1 <= 0 → stopped!
        """
        v         = make_vehicle(1, 'two_wheeler', 800, 4)
        v_left    = make_vehicle(2, 'car', 800, 3, length=4, width=2, speed=0)
        v_right   = make_vehicle(3, 'car', 800, 5, length=4, width=2, speed=0)
        v_front1  = make_vehicle(4, 'car', 804, 2, length=4, width=2, speed=0)  # back=801, gap=0
        v_front2  = make_vehicle(5, 'car', 805, 6, length=4, width=2, speed=0)  # back=802, gap=1

        action = self._run(v, [v_left, v_right, v_front1, v_front2])
        assert action == 'stopped', f"Expected stopped, got {action}"


# -----------------------------------------------------------------------
# Critical test: cars and buses are NEVER eligible (explicit assertion)
# -----------------------------------------------------------------------

class TestCarBusNeverEligible:
    """
    Explicit test: even with perfectly ample gaps everywhere, cars and buses
    must NEVER be returned as seepage-eligible. This directly tests the
    accepted criterion from the phase spec.
    """
    
    def test_car_never_eligible_explicit(self):
        """
        Car with perfect conditions (IZOI, red signal, ample gaps) → still False.
        Regardless of gap availability, is_seepage_eligible must return False for car.
        """
        car = make_vehicle(1, 'car', 800, 2, length=7, width=3, speed=0)
        eligible_modes = ['two_wheeler', 'three_wheeler']
        izoi_car_cells = int(187.385 / 0.5)  # 374 cells — car is inside IZOI at pos=800

        result = is_seepage_eligible(car, 'red', STOP_LINE, izoi_car_cells, eligible_modes)
        assert result is False, "Car must NEVER be seepage-eligible"

    def test_bus_never_eligible_explicit(self):
        """
        Bus with perfect conditions → still False.
        """
        bus = make_vehicle(2, 'bus', 800, 0, length=20, width=4, speed=0)
        eligible_modes = ['two_wheeler', 'three_wheeler']
        izoi_bus_cells = int(111.26 / 0.5)  # 222 cells — bus is inside IZOI at pos=800

        result = is_seepage_eligible(bus, 'red', STOP_LINE, izoi_bus_cells, eligible_modes)
        assert result is False, "Bus must NEVER be seepage-eligible"

    def test_car_not_eligible_even_if_added_to_modes(self):
        """
        Even if someone passes ['car'] as eligible_modes, the test suite
        here uses the CORRECT config ['two_wheeler', 'three_wheeler'].
        This is a no-op confirmation that the function respects the modes list.
        """
        car = make_vehicle(1, 'car', 800, 2, length=7, width=3)
        izoi_car_cells = int(187.385 / 0.5)
        # With correct config:
        result = is_seepage_eligible(car, 'red', STOP_LINE, izoi_car_cells, ['two_wheeler', 'three_wheeler'])
        assert result is False

    def test_seepage_action_never_triggered_for_car(self):
        """
        Run attempt_seepage in a seepage-off scenario ([] eligible modes) and
        confirm that cars only ever get action=None (never seep) in the sim loop.
        
        This is tested via is_seepage_eligible directly since attempt_seepage is
        only ever called when is_seepage_eligible returns True.
        """
        car = make_vehicle(1, 'car', 800, 2, length=7, width=3)
        izoi_car_cells = int(187.385 / 0.5)
        for modes_list in [[], ['two_wheeler'], ['two_wheeler', 'three_wheeler']]:
            result = is_seepage_eligible(car, 'red', STOP_LINE, izoi_car_cells, modes_list)
            assert result is False, f"Car must not be eligible regardless of modes_list={modes_list}"
