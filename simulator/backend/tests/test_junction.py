"""
test_junction.py — Stage 3 junction routing tests.

Covers: proportion-sum validation, and a statistical test that observed turn
frequencies match the configured proportions within tolerance.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.junction import Junction
from src.network import grid_builder


def test_proportions_must_sum_to_one():
    j = Junction(id=0, x=0, y=0, turns={0: {1: 0.5, 2: 0.3}})  # sums to 0.8
    with pytest.raises(ValueError):
        j.validate()


def test_valid_proportions_pass():
    j = Junction(id=0, x=0, y=0, turns={0: {1: 0.6, 2: 0.4}})
    j.validate()  # should not raise


def test_negative_proportion_rejected():
    j = Junction(id=0, x=0, y=0, turns={0: {1: 1.2, 2: -0.2}})
    with pytest.raises(ValueError):
        j.validate()


def test_choose_out_frequencies_match_proportions():
    """Weighted routing: observed out-road frequencies ≈ configured proportions."""
    j = Junction(id=0, x=0, y=0, turns={0: {1: 0.7, 2: 0.3}})
    j.validate()
    rng = np.random.default_rng(123)
    N = 20000
    counts = {1: 0, 2: 0}
    for _ in range(N):
        counts[j.choose_out(0, rng)] += 1
    f1 = counts[1] / N
    f2 = counts[2] / N
    assert abs(f1 - 0.7) < 0.02, f1
    assert abs(f2 - 0.3) < 0.02, f2


def test_all_five_configs_build_and_validate():
    for name in [
        "one_way",
        "two_way_no_interaction",
        "two_way_turns",
        "two_way_bidirectional_turns",
        "grid",
    ]:
        net = grid_builder.build(name)
        net.validate()
        assert len(net.roads) >= 1


def test_turn_frequencies_observed_in_integration():
    """
    Integration: case 3 has a single incoming stream (road 0) splitting at
    the junction into a straight road (1) and a turn road (2). Count distinct
    vehicles arriving on each and confirm the split tracks straight_bias.
    (A symmetric junction would wash this out; case 3 is asymmetric so the
    observed split directly reflects the configured proportions.)
    """
    bias = 0.75
    net = grid_builder.build_two_way_turns(seg=60, straight_bias=bias,
                                           source_rate=0.6, car_fraction=0.0)
    rng = np.random.default_rng(7)
    seen_straight: set = set()
    seen_turn: set = set()
    for _ in range(6000):
        net.step(rng)
        for v in net.roads[1].vehicles:   # straight sink
            seen_straight.add(v.id)
        for v in net.roads[2].vehicles:   # turn sink
            seen_turn.add(v.id)
    total = len(seen_straight) + len(seen_turn)
    assert total > 300, f"too few exits to be statistical: {total}"
    frac_straight = len(seen_straight) / total
    assert abs(frac_straight - bias) < 0.05, frac_straight
