"""
test_entropy.py — Stage 5 Shannon-entropy tests with hand-computable fixtures.

The key property (plan.md §8.4): evenly-spread traffic has HIGH entropy,
clustered traffic has LOW entropy. Fixtures below have exact expected values.
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.analytics.entropy import shannon_entropy, network_entropy
from src.analytics.heatmap import segment_densities


def _occ(length, positions):
    a = np.zeros(length, dtype=np.int8)
    a[list(positions)] = 1
    return a


# window_size = 10, length = 40 → B = 4 bins
def test_even_spread_is_maximum_entropy():
    # one vehicle in each of the 4 bins → uniform → H = log2(4) = 2 bits, norm = 1
    occ = _occ(40, [0, 10, 20, 30])
    h_bits, h_norm = shannon_entropy(occ, window_size=10)
    assert abs(h_bits - 2.0) < 1e-9
    assert abs(h_norm - 1.0) < 1e-9


def test_fully_clustered_is_zero_entropy():
    # all 4 vehicles in bin 0 → H = 0
    occ = _occ(40, [0, 1, 2, 3])
    h_bits, h_norm = shannon_entropy(occ, window_size=10)
    assert h_bits == 0.0
    assert h_norm == 0.0


def test_half_half_is_one_bit():
    # vehicles in bins 0 and 1 only, equal counts → H = 1 bit, norm = 0.5
    occ = _occ(40, [0, 1, 10, 11])
    h_bits, h_norm = shannon_entropy(occ, window_size=10)
    assert abs(h_bits - 1.0) < 1e-9
    assert abs(h_norm - 0.5) < 1e-9


def test_empty_road_is_zero():
    assert shannon_entropy(np.zeros(40, dtype=np.int8), 10) == (0.0, 0.0)


def test_spread_beats_clustered_general():
    """Sanity across a range: spread entropy strictly exceeds clustered."""
    rng = np.random.default_rng(0)
    L = 200
    spread = _occ(L, rng.choice(L, size=40, replace=False))
    clustered = _occ(L, range(40))  # first 40 cells packed
    _, hs = shannon_entropy(spread, 10)
    _, hc = shannon_entropy(clustered, 10)
    assert hs > hc
    assert hs > 0.8   # spread is near-uniform
    assert hc < 0.5   # clustered is low


def test_network_entropy_pools_roads():
    a = _occ(20, [0, 10])   # 2 bins, 1 each
    b = _occ(20, [0, 10])
    h_bits, h_norm = network_entropy([a, b], window_size=10)
    # 4 bins, 1 vehicle each → uniform → H = log2(4) = 2, norm = 1
    assert abs(h_bits - 2.0) < 1e-9
    assert abs(h_norm - 1.0) < 1e-9


def test_segment_densities_shape_and_values():
    occ = _occ(25, [0, 1, 2, 3, 4])  # first 5 of 25 occupied
    segs = segment_densities(occ, window=10)
    assert len(segs) == 3               # 25 -> segments of 10,10,5
    assert segs[0]["d"] == 0.5          # 5/10 occupied in first segment
    assert segs[1]["d"] == 0.0
    assert segs[2]["n"] == 5            # last partial segment length
