"""
test_landscape.py — Stage 6 landscape classification tests.

Uses the empirically-derived thresholds (see landscape.py docstring and
derive_landscape_thresholds.py). At least one clear case per category, plus
the monotonicity property that motivated the design (more congestion stress
never yields a *less* severe label).
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.network.landscape import classify_landscape, congestion_stress


def test_trivial_case():
    # nearly-empty free-flowing road: low density, no blockage, no queues
    assert classify_landscape(density=0.08, blocked_fraction=0.0, avg_queue_length=0.0) == "trivial"


def test_average_case():
    # moderate occupancy (~peak-flow region), no blockage/queues → density
    # stress ≈ (0.5-0.15)/0.6 ≈ 0.58 → average
    assert classify_landscape(density=0.50, blocked_fraction=0.0, avg_queue_length=0.0) == "average"


def test_worst_case_by_density():
    # heavily jammed lane (ρ ≥ 0.75) → full density stress → worst
    assert classify_landscape(density=0.80, blocked_fraction=0.0, avg_queue_length=0.0) == "worst"


def test_worst_case_by_blockage():
    # 3% of cells blocked collapses flow (measured eff ~0.22) → worst
    assert classify_landscape(density=0.30, blocked_fraction=0.03, avg_queue_length=0.0) == "worst"


def test_worst_case_by_queue():
    # junction lanes fully backed up (avg queue = QUEUE_WINDOW) → worst
    assert classify_landscape(density=0.30, blocked_fraction=0.0, avg_queue_length=12.0) == "worst"


def test_monotonic_in_each_input():
    base = congestion_stress(0.3, 0.0, 0.0)
    assert congestion_stress(0.6, 0.0, 0.0) >= base
    assert congestion_stress(0.3, 0.02, 0.0) >= base
    assert congestion_stress(0.3, 0.0, 8.0) >= base


def test_stress_bounds():
    assert congestion_stress(0.0, 0.0, 0.0) == 0.0
    assert congestion_stress(1.0, 1.0, 100.0) == 1.0
