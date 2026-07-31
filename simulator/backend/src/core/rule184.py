"""
rule184.py — Rule 184 synchronous update for a 1D binary road array.

Rule 184 is elementary CA rule 184.  For a binary (0/1) cell at
position i with left neighbour L and right neighbour R, the complete
transition table (184 = 0b10111000) is:

  LCR  ->  new_C
  ---      -----
  111       1    (vehicle blocked by vehicle ahead)
  110       0    (vehicle moves right into gap)
  101       1    (gap fills: vehicle arrives from left)
  100       1    (gap fills: vehicle arrives from left, gap at right)
  011       1    (vehicle blocked)
  010       0    (vehicle moves right)
  001       0    (empty, no vehicle from left)
  000       0    (empty)

The compact formula (verified against all 8 table entries):

    new_C = (C AND R) OR (L AND NOT C)

  - A vehicle (C=1) stays only if it is blocked (R=1): C&R.
  - An empty cell (C=0) fills if the left neighbour has a vehicle
    (L=1) and can advance into it: L & ~C = L & 1 = L when C=0.

Traffic interpretation:
  - Vehicles move rightward at speed 1 whenever the cell ahead is empty.
  - Updates are simultaneous (synchronous): one read-only snapshot of
    the previous state is used to compute the entire next state, with
    no in-place mutation mid-step (plan.md §5, non-negotiable).

References
----------
- Wolfram, S. (1986). Theory and Applications of Cellular Automata.
- Nagel, K., & Schreckenberg, M. (1992). NaSch rule reduces to Rule 184
  for v_max=1 and p=0.
"""

from __future__ import annotations

import numpy as np


def step(state: np.ndarray, periodic: bool = True) -> np.ndarray:
    """
    Apply one synchronous Rule 184 step.

    Parameters
    ----------
    state    : 1D int8 (or int) array; 0 = empty, 1 = vehicle.
    periodic : if True use ring (periodic) boundary; if False use open
               boundary (leftmost cell always gets L=0, rightmost cell
               always gets R=0).

    Returns
    -------
    new_state : same dtype and shape as `state`, fully computed before
                any element is written (no aliasing with `state`).
    """
    n = len(state)
    s = state.astype(np.int8, copy=False)  # ensure correct dtype view

    if periodic:
        # np.roll is read-only w.r.t. `s`; both shift arrays are derived
        # from the unmodified `s`.
        left  = np.roll(s, 1)   # s[i-1]
        right = np.roll(s, -1)  # s[i+1]
    else:
        # Open boundaries: ghost cells are always empty.
        left  = np.empty(n, dtype=np.int8)
        right = np.empty(n, dtype=np.int8)
        left[0]    = 0
        left[1:]   = s[:-1]
        right[-1]  = 0
        right[:-1] = s[1:]

    # Rule 184: new_C = (C & R) | (L & ~C)
    # Verified against all 8 entries of the truth table.
    # Using bitwise integer ops on int8 arrays — fully vectorised, no loop.
    # ~s on int8 gives -1-s, so we mask with & 1 to get a 0/1 result.
    not_s = (~s) & np.int8(1)   # bitwise NOT then mask: 0→1, 1→0
    new_state = ((s & right) | (left & not_s)).astype(np.int8)
    return new_state


def run(
    state: np.ndarray,
    n_steps: int,
    periodic: bool = True,
) -> np.ndarray:
    """
    Run the automaton for `n_steps` steps and return the final state.

    This is a convenience wrapper around `step`; it does not store
    intermediate states (call it repeatedly with snapshot storage if
    you need trajectory data).
    """
    for _ in range(n_steps):
        state = step(state, periodic=periodic)
    return state


def run_collect(
    state: np.ndarray,
    n_steps: int,
    periodic: bool = True,
) -> np.ndarray:
    """
    Run the automaton for `n_steps` steps, collecting every state
    (including the initial one) in a 2D array of shape (n_steps+1, N).
    """
    N = len(state)
    history = np.empty((n_steps + 1, N), dtype=np.int8)
    history[0] = state
    for t in range(1, n_steps + 1):
        state = step(state, periodic=periodic)
        history[t] = state
    return history
