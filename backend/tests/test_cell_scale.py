"""
test_cell_scale.py — Stage 8 cell-scale tests.

Asserts the meters-to-cells conversion is monotonic and produces sane
results across a range of realistic road lengths, from very short campus
paths through longer city roads.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.mapdata.cell_scale import meters_to_cells, haversine, METERS_PER_CELL, MIN_CELLS


# ---- monotonicity ----

def test_monotonic_increasing():
    """Longer roads must produce equal or more cells."""
    prev = 0
    for m in range(1, 2000, 7):
        c = meters_to_cells(float(m))
        assert c >= prev, f"{m}m → {c} cells, but previous was {prev}"
        prev = c


def test_zero_meters_gives_one_cell():
    """Zero meters should still produce at least 1 cell."""
    assert meters_to_cells(0.0) >= 1


def test_very_small_gives_one_cell():
    assert meters_to_cells(0.5) >= 1


# ---- realistic road lengths ----

def test_short_campus_road():
    """50m campus path → should be ~7 cells (enough for dynamics)."""
    c = meters_to_cells(50.0)
    assert 5 <= c <= 10, f"50m → {c} cells"


def test_campus_main_avenue():
    """200m avenue → should be ~27 cells."""
    c = meters_to_cells(200.0)
    assert 20 <= c <= 35, f"200m → {c} cells"


def test_city_block():
    """300m city block → ~40 cells."""
    c = meters_to_cells(300.0)
    assert 30 <= c <= 50, f"300m → {c} cells"


def test_long_road():
    """1 km road → ~133 cells, still manageable."""
    c = meters_to_cells(1000.0)
    assert 100 <= c <= 200, f"1000m → {c} cells"


# ---- rounding correctness ----

def test_exact_multiple():
    """Exact multiple of METERS_PER_CELL rounds cleanly."""
    c = meters_to_cells(METERS_PER_CELL * 10)
    assert c == 10


def test_half_cell_rounds_up():
    """Half a cell rounds to 1."""
    c = meters_to_cells(METERS_PER_CELL * 0.5)
    assert c >= 1


# ---- haversine ----

def test_haversine_same_point():
    d = haversine(25.0, 83.0, 25.0, 83.0)
    assert d == pytest.approx(0.0, abs=0.01)


def test_haversine_known_distance():
    """IIT BHU (25.262, 82.991) to Varanasi Junction (~25.317, 83.010):
    roughly 6-7 km.
    """
    d = haversine(25.262, 82.991, 25.317, 83.010)
    assert 5_000 < d < 8_000, f"distance = {d:.0f} m"


def test_haversine_symmetry():
    d1 = haversine(25.0, 83.0, 26.0, 84.0)
    d2 = haversine(26.0, 84.0, 25.0, 83.0)
    assert d1 == pytest.approx(d2, rel=1e-12)
