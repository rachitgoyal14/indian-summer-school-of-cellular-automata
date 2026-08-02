"""
density.py (minimal, Stage 1) — flow and density analytics.

Flow is measured as the number of vehicles that cross a reference
boundary per time step, averaged over a measurement window.

For a periodic (ring) road, the crossing rate at the right boundary of
cell i equals the number of steps where state[i]=1 AND state[i+1]=0
(a vehicle moved forward), averaged per step.  We use cell -1→0 as the
canonical crossing point, but averaging over all cells gives the same
result by translation invariance and is numerically cleaner.
"""

from __future__ import annotations

import numpy as np


def density_of(state: np.ndarray) -> float:
    """Return the fraction of occupied cells in `state`."""
    return float(state.sum()) / len(state)


def flow_at_step(
    state_before: np.ndarray,
    state_after: np.ndarray,
) -> float:
    """
    Estimate the instantaneous flow (vehicles / cell / step) from one
    Rule 184 step.

    Under Rule 184 a vehicle moves from cell i to i+1 iff state_before[i]=1
    and state_before[i+1]=0.  The flow past a single reference boundary
    (i → i+1) is exactly:

        f = state_before[i] * (1 - state_before[i+1])

    Averaging this over ALL boundaries (i = 0..N-1, with wrap-around for
    periodic case) gives a cleaner estimate than a single boundary:

        f_avg = mean_i( state_before[i] * (1 - state_before[(i+1) % N]) )

    which equals mean_i( state_before[i] AND NOT state_before[(i+1)] ).

    Parameters
    ----------
    state_before : road state at time t
    state_after  : road state at time t+1 (used only to choose boundary)

    Returns
    -------
    Instantaneous flow in vehicles / cell / step.
    """
    n = len(state_before)
    right = np.roll(state_before, -1)          # state_before[(i+1) % N]
    crossings = state_before & (~right & 1)    # vehicle present AND gap ahead
    return float(crossings.sum()) / n


def measure_flow(
    states: np.ndarray,
) -> tuple[float, float]:
    """
    Compute mean and std of per-step flow over a trajectory.

    Parameters
    ----------
    states : 2D array of shape (T, N), row t is the state at step t.
             Must have at least 2 rows.

    Returns
    -------
    (mean_flow, std_flow) — both in vehicles / cell / step.
    """
    T = states.shape[0]
    flows = np.array(
        [flow_at_step(states[t], states[t + 1]) for t in range(T - 1)]
    )
    return float(flows.mean()), float(flows.std())
