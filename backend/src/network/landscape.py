"""
landscape.py — trivial / average / worst landscape classification (Stage 6).

The brief wants a quick read on whether a layout is fine, getting busy, or
collapsing ("plan, reorganize, redesign, and collapse avenues"). We classify
from three network-wide stress signals — density, blocked-cell fraction, and
average junction queue — into: "trivial", "average", "worst".

Why not flow?  `derive_landscape_thresholds.py` sweeps real runs and shows the
obvious ground truth (flow efficiency) is *non-monotonic*: on a Rule 184 ring
flow = min(ρ, 1−ρ), so a nearly-empty road (ρ=0.05) has low flow yet is
clearly *trivial*, not worst.  So we classify by **congestion stress**, which
IS monotonic in each input (more density / more blockage / longer queues = worse).

Thresholds, read off `derive_landscape_thresholds.py` output:
  - density stress ramps 0.15 → 0.75: below ~0.15 the road is nearly empty
    (trivial); the Rule 184 jam branch (ρ>0.5) degrades flow and by ρ≈0.75 the
    lane is heavily jammed (measured efficiency ≤ 0.4).
  - blocked-fraction stress saturates at 0.03: the sweep showed 2–3 % of cells
    blocked already crushes flow efficiency to ~0.22–0.25.
  - queue stress saturates at QUEUE_WINDOW (12 cells): grid runs under heavy
    load plateaued at avg queue ≈ 12.6–12.8, i.e. the incoming lanes' queue
    windows fully backed up.

The overall stress is the WORST (max) of the three normalised stresses — a
planner cares if *any* dimension is bad — bucketed at 1/3 and 2/3.
"""

from __future__ import annotations

# empirically-derived calibration constants (see module docstring + script)
DENSITY_LOW = 0.15   # below this the road is nearly empty → no stress
DENSITY_HIGH = 0.75  # at/above this the lane is heavily jammed → full stress
BLOCKED_FULL = 0.03  # blocked fraction that already collapses flow
QUEUE_FULL = 12.0    # avg junction queue at which lanes are fully backed up

TRIVIAL_MAX = 1.0 / 3.0  # stress < 1/3 → trivial
WORST_MIN = 2.0 / 3.0    # stress ≥ 2/3 → worst


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def congestion_stress(
    density: float, blocked_fraction: float, avg_queue_length: float
) -> float:
    """Return the overall congestion stress ∈ [0, 1] (max of the three)."""
    density_stress = _clamp01((density - DENSITY_LOW) / (DENSITY_HIGH - DENSITY_LOW))
    blocked_stress = _clamp01(blocked_fraction / BLOCKED_FULL)
    queue_stress = _clamp01(avg_queue_length / QUEUE_FULL)
    return max(density_stress, blocked_stress, queue_stress)


def classify_landscape(
    density: float, blocked_fraction: float, avg_queue_length: float
) -> str:
    """Classify the network state as 'trivial', 'average', or 'worst'."""
    s = congestion_stress(density, blocked_fraction, avg_queue_length)
    if s < TRIVIAL_MAX:
        return "trivial"
    if s < WORST_MIN:
        return "average"
    return "worst"
