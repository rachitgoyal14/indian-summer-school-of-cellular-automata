"""
entropy.py — Shannon entropy of the spatial traffic distribution (Stage 5).

We measure how *spread out* the vehicles are. The road is divided into bins of
`window_size` cells; the per-bin vehicle counts form a probability distribution
p_i = (vehicles in bin i) / (total vehicles); the Shannon entropy is

    H = -Σ p_i · log2(p_i)      (bits)

Interpretation (this is the whole point — plan.md §8.4):
  - vehicles spread evenly across all B bins → p uniform → H = log2(B) (maximal)
  - vehicles clustered into one bin        → H = 0 (minimal)

So when a disruption bunches traffic up, H visibly drops. We also return a
normalised entropy H / log2(B) ∈ [0, 1] which is what the UI shows, since it is
directly comparable across networks of different sizes.
"""

from __future__ import annotations

import numpy as np


def shannon_entropy(
    occupancy: np.ndarray, window_size: int = 10
) -> tuple[float, float]:
    """
    Return (H_bits, H_normalised) for a 1D occupancy array.

    H_normalised is H / log2(B) where B is the number of bins, so 1.0 means
    perfectly even spread and 0.0 means fully clustered. Empty roads → (0, 0).
    """
    n = len(occupancy)
    if n == 0:
        return 0.0, 0.0
    window_size = max(1, int(window_size))
    n_bins = int(np.ceil(n / window_size))
    # sum occupancy within each bin
    counts = np.zeros(n_bins, dtype=float)
    for b in range(n_bins):
        counts[b] = float(occupancy[b * window_size : (b + 1) * window_size].sum())

    total = counts.sum()
    if total <= 0:
        return 0.0, 0.0

    p = counts[counts > 0] / total
    h_bits = float(-(p * np.log2(p)).sum())
    denom = np.log2(n_bins) if n_bins > 1 else 1.0
    h_norm = float(h_bits / denom) if denom > 0 else 0.0
    return h_bits, h_norm


def network_entropy(
    occupancies: list[np.ndarray], window_size: int = 10
) -> tuple[float, float]:
    """Network-wide entropy: bin every road's occupancy and pool the bins."""
    if not occupancies:
        return 0.0, 0.0
    window_size = max(1, int(window_size))
    counts: list[float] = []
    for occ in occupancies:
        n_bins = int(np.ceil(len(occ) / window_size))
        for b in range(n_bins):
            counts.append(float(occ[b * window_size : (b + 1) * window_size].sum()))
    arr = np.array(counts, dtype=float)
    total = arr.sum()
    if total <= 0 or len(arr) == 0:
        return 0.0, 0.0
    p = arr[arr > 0] / total
    h_bits = float(-(p * np.log2(p)).sum())
    denom = np.log2(len(arr)) if len(arr) > 1 else 1.0
    h_norm = float(h_bits / denom) if denom > 0 else 0.0
    return h_bits, h_norm
