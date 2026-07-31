"""
cell.py — Road cell array representation.

A road is a 1D NumPy integer array where:
  0 = empty cell
  1 = occupied cell (any vehicle type, in Stage 1)

In later stages, values > 1 will encode vehicle type/ID; for now
the array is binary (0/1) which is exactly what Rule 184 requires.
"""

from __future__ import annotations

import numpy as np


def empty_road(length: int) -> np.ndarray:
    """Return a zero-filled road array of the given length."""
    return np.zeros(length, dtype=np.int8)


def random_initial_state(
    length: int,
    density: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Return a road of `length` cells with exactly round(density * length)
    vehicles placed uniformly at random (without replacement).

    Parameters
    ----------
    length  : number of cells
    density : target vehicle density in [0, 1]
    rng     : a numpy Generator (e.g. np.random.default_rng(seed))

    Returns
    -------
    1D int8 array with exactly n_vehicles ones, rest zeros.
    """
    if not 0.0 <= density <= 1.0:
        raise ValueError(f"density must be in [0, 1], got {density!r}")

    n_vehicles = round(density * length)
    n_vehicles = min(n_vehicles, length)   # guard against fp rounding edge

    state = np.zeros(length, dtype=np.int8)
    occupied = rng.choice(length, size=n_vehicles, replace=False)
    state[occupied] = 1
    return state


def density_of(state: np.ndarray) -> float:
    """Return the fraction of occupied cells."""
    return float(state.sum()) / len(state)
