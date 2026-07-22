"""
Tests for Phase 5 seepage gap functions (seepage_lateral_gap, seepage_longitudinal_gap).

Three fixtures per function:
  (a) ample gap on both sides — returns correct positive values
  (b) blocked on both sides — returns ~0 (no seep)
  (c) asymmetric gap — room on right, not left — returns correctly
"""

import pytest
from src.core.vehicle import Vehicle
from src.core.gaps import seepage_lateral_gap, seepage_longitudinal_gap


def make_vehicle(vid, pos, lat, length, width):
    return Vehicle(
        id=vid, mode="car",
        length_cells=length, width_cells=width,
        max_speed_cells_per_step=10, max_accel_cells_per_step2=1,
        position_cells=pos, lateral_position_cells=lat,
        speed_cells_per_step=0,  # stopped at red
    )


# ---------------------------------------------------------------------------
# seepage_lateral_gap tests
# ---------------------------------------------------------------------------

class TestSeepageLateralGap:
    """
    Geometry for all tests:
    v_main: pos=50, len=4, lat=4, width=1 → footprint: long=[47,50], lat=[4,4]

    Eq 4: lateral_gap = min(d4, d3) where d4=left-clearance, d3=right-clearance.
    """

    def test_ample_gap_both_sides(self):
        """
        (a) Ample gap on both sides → both return positive values.
        
        left_vehicle: lat=0, width=2 → right edge at lat=1. Gap left = 4 - 1 - 1 = 2
        right_vehicle: lat=7, width=2 → left edge at lat=7. Gap right = 7 - 4 - 1 = 2
        """
        v_main = make_vehicle(1, 50, 4, 4, 1)
        v_left  = make_vehicle(2, 50, 0, 4, 2)   # right edge = 1
        v_right = make_vehicle(3, 50, 7, 4, 2)   # left edge  = 7

        gap_l, gap_r = seepage_lateral_gap(v_main, [v_left, v_right])
        assert gap_l == pytest.approx(2.0), f"Expected gap_left=2, got {gap_l}"
        assert gap_r == pytest.approx(2.0), f"Expected gap_right=2, got {gap_r}"

    def test_blocked_both_sides(self):
        """
        (b) Blocked on both sides → returns 0 (or near-0).
        
        left_vehicle: lat=3, width=2 → right edge=4. But v_main lat=4, so lateral overlap → 0.
        """
        v_main  = make_vehicle(1, 50, 4, 4, 1)
        v_left  = make_vehicle(2, 50, 3, 4, 2)   # right edge=4, overlaps main → blocked
        v_right = make_vehicle(3, 50, 5, 4, 2)   # left edge=5, overlaps main → blocked

        gap_l, gap_r = seepage_lateral_gap(v_main, [v_left, v_right])
        assert gap_l == 0.0
        assert gap_r == 0.0

    def test_asymmetric_room_right_not_left(self):
        """
        (c) Room on right but not left.
        
        left_vehicle  at lat=3, width=2 → right edge=4. Gap left = 4 - 4 - 1 = -1 → clamped to 0
        right_vehicle at lat=7, width=1 → left edge=7.  Gap right = 7 - 4 - 1 = 2
        """
        v_main  = make_vehicle(1, 50, 4, 4, 1)
        v_left  = make_vehicle(2, 50, 3, 4, 2)   # right edge=4, directly adjacent (gap=−1 → 0)
        v_right = make_vehicle(3, 50, 7, 4, 1)   # left edge=7, gap right = 2

        gap_l, gap_r = seepage_lateral_gap(v_main, [v_left, v_right])
        # left is blocked (overlap), right has clearance
        assert gap_l == 0.0, f"Expected gap_left=0 (blocked), got {gap_l}"
        assert gap_r == pytest.approx(2.0), f"Expected gap_right=2, got {gap_r}"

    def test_no_longitudinal_overlap_ignored(self):
        """
        Vehicles that do NOT share longitudinal extent with v_main must not affect lateral gap.
        
        A vehicle far ahead (pos=200) should be invisible to seepage_lateral_gap.
        """
        v_main = make_vehicle(1, 50, 4, 4, 1)
        v_far  = make_vehicle(2, 200, 0, 4, 2)   # completely ahead, no overlap

        gap_l, gap_r = seepage_lateral_gap(v_main, [v_far])
        assert gap_l == float('inf')
        assert gap_r == float('inf')

    def test_no_neighbors(self):
        """No neighbors → inf on both sides."""
        v_main = make_vehicle(1, 50, 4, 4, 1)
        gap_l, gap_r = seepage_lateral_gap(v_main, [])
        assert gap_l == float('inf')
        assert gap_r == float('inf')


# ---------------------------------------------------------------------------
# seepage_longitudinal_gap tests
# ---------------------------------------------------------------------------

class TestSeepageLongitudinalGap:
    """
    Geometry:
    v_main: pos=50, len=4 → front at 50.

    Eq 5: longitudinal_gap = min(d1, d2) where d1,d2 = forward clearances
    to the two nearest front vehicles.
    """

    def test_ample_gap_two_front_vehicles(self):
        """
        (a) Two front vehicles with ample gap.
        
        v_front1: pos=60, len=4 → back at 57. Gap1 = 57 - 50 - 1 = 6
        v_front2: pos=65, len=4 → back at 62. Gap2 = 62 - 50 - 1 = 11
        min = 6
        """
        v_main   = make_vehicle(1, 50, 4, 4, 1)
        v_front1 = make_vehicle(2, 60, 3, 4, 1)  # back=57
        v_front2 = make_vehicle(3, 65, 5, 4, 1)  # back=62

        gap = seepage_longitudinal_gap(v_main, [v_front1, v_front2])
        assert gap == pytest.approx(6.0), f"Expected long_gap=6, got {gap}"

    def test_blocked_both_front_vehicles_close(self):
        """
        (b) Both front vehicles very close → small gap.
        
        v_front1: pos=52, len=4 → back=49. Gap1 = 49 - 50 - 1 = -2 → 0 effective
        Actually back=49 < front=50, meaning vehicle is behind (no gap ahead).
        Use pos=55: back=52. Gap1 = 52 - 50 - 1 = 1
        v_front2: pos=56, len=4 → back=53. Gap2 = 53 - 50 - 1 = 2
        min = 1
        """
        v_main   = make_vehicle(1, 50, 4, 4, 1)
        v_front1 = make_vehicle(2, 55, 3, 4, 1)   # back=52, gap=1
        v_front2 = make_vehicle(3, 56, 5, 4, 1)   # back=53, gap=2

        gap = seepage_longitudinal_gap(v_main, [v_front1, v_front2])
        assert gap == pytest.approx(1.0), f"Expected long_gap=1, got {gap}"

    def test_asymmetric_one_close_one_far(self):
        """
        (c) One close front vehicle (gap=2), one far (gap=20) → min=2.
        """
        v_main   = make_vehicle(1, 50, 4, 4, 1)
        v_close  = make_vehicle(2, 53, 3, 4, 1)   # back=50, gap=0... wait
        # back = pos - len + 1 = 53 - 4 + 1 = 50. gap = 50 - 50 - 1 = -1 → not ahead
        # Use pos=54: back=51. gap = 51 - 50 - 1 = 0
        # Use pos=55: back=52. gap=1
        # Use pos=56: back=53. gap=2
        v_close  = make_vehicle(2, 56, 3, 4, 1)   # gap=2
        v_far    = make_vehicle(3, 75, 5, 4, 1)    # back=72, gap=21

        gap = seepage_longitudinal_gap(v_main, [v_close, v_far])
        assert gap == pytest.approx(2.0), f"Expected long_gap=2, got {gap}"

    def test_fewer_than_two_front_vehicles_returns_inf(self):
        """
        (a-edge) With fewer than 2 front vehicles, diagonal seep is vacuous → inf.
        """
        v_main   = make_vehicle(1, 50, 4, 4, 1)
        v_front1 = make_vehicle(2, 60, 3, 4, 1)

        gap = seepage_longitudinal_gap(v_main, [v_front1])
        assert gap == float('inf'), "Need 2+ front vehicles for diagonal gap"

    def test_no_front_vehicles(self):
        """No neighbors → inf."""
        v_main = make_vehicle(1, 50, 4, 4, 1)
        gap = seepage_longitudinal_gap(v_main, [])
        assert gap == float('inf')
