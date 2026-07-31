"""
heatmap.py — per-road-segment congestion values (Stage 5).

Each road is divided into fixed-length segments; each segment's congestion is
its local vehicle density (occupied cells / segment length) ∈ [0, 1]. These
values drive the frontend heatmap overlay (green = free-flowing, red = jammed)
and are cross-checkable against the vehicles visible in the main view.
"""

from __future__ import annotations

import numpy as np

HEATMAP_WINDOW = 10  # cells per congestion segment


def segment_densities(occupancy: np.ndarray, window: int = HEATMAP_WINDOW) -> list[dict]:
    """
    Return a list of segments [{"s": start, "n": length, "d": density}] for a
    1D occupancy array. Density is the fraction of occupied cells in the segment.
    """
    n = len(occupancy)
    if n == 0:
        return []
    window = max(1, int(window))
    segments: list[dict] = []
    for start in range(0, n, window):
        seg = occupancy[start : start + window]
        segments.append(
            {"s": int(start), "n": int(len(seg)), "d": round(float(seg.mean()), 4)}
        )
    return segments
