"""
test_rule184.py — Stage 1 acceptance tests for the Rule 184 engine.

Tests are ordered from simplest (unit) to most complex (mathematical
correctness).  The simultaneous-vs-sequential test is the most important:
it is the one test that distinguishes the correct synchronous update from
an incorrect sequential update, as required by stages.md Stage 1.

Rule 184 truth table (184 = 0b10111000):
  LCR=111→1, 110→0, 101→1, 100→1, 011→1, 010→0, 001→0, 000→0

Compact formula (verified against all 8 entries):
  new_C = (C AND R) OR (L AND NOT C)
"""

from __future__ import annotations

import sys
import os

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or from tests/ directly
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.cell import random_initial_state, density_of, empty_road
from src.core.rule184 import step, run, run_collect
from src.analytics.density import flow_at_step, measure_flow


# ===========================================================================
# Helpers
# ===========================================================================

def _s(lst):
    return np.array(lst, dtype=np.int8)


# ===========================================================================
# 1. Hand-computable unit tests for step()
#    All expected values derived from the Rule 184 truth table above.
# ===========================================================================

class TestStep:

    # -----------------------------------------------------------------------
    # 1a. Single vehicle on a ring road: moves one step per tick.
    # -----------------------------------------------------------------------
    def test_single_vehicle_moves_right(self):
        """A lone vehicle on a ring road advances by one cell each step."""
        state = _s([0, 0, 1, 0, 0])
        after = step(state, periodic=True)
        expected = _s([0, 0, 0, 1, 0])
        np.testing.assert_array_equal(after, expected)

    def test_single_vehicle_wraps_around(self):
        """A lone vehicle at the rightmost cell wraps to cell 0."""
        state = _s([0, 0, 0, 0, 1])
        after = step(state, periodic=True)
        expected = _s([1, 0, 0, 0, 0])
        np.testing.assert_array_equal(after, expected)

    # -----------------------------------------------------------------------
    # 1b. Fully occupied road: no vehicle can move.
    # -----------------------------------------------------------------------
    def test_full_road_does_not_change(self):
        """All cells occupied → no vehicle has a gap to move into."""
        state = _s([1, 1, 1, 1, 1])
        after = step(state, periodic=True)
        np.testing.assert_array_equal(after, state)

    # -----------------------------------------------------------------------
    # 1c. Empty road: stays empty.
    # -----------------------------------------------------------------------
    def test_empty_road_stays_empty(self):
        state = _s([0, 0, 0, 0, 0])
        after = step(state, periodic=True)
        np.testing.assert_array_equal(after, state)

    # -----------------------------------------------------------------------
    # 1d. Alternating [1, 0, 1, 0] — period-2 oscillation.
    # -----------------------------------------------------------------------
    def test_alternating_period_2_oscillation(self):
        """
        [1, 0, 1, 0] → [0, 1, 0, 1] under periodic boundary.
        Every vehicle advances one step; this is a period-2 oscillation.

        Hand-check with new_C = (C&R) | (L&~C):
          i=0: C=1, L=state[3]=0, R=state[1]=0 → (1&0)|(0&0)=0  (vehicle moves)
          i=1: C=0, L=state[0]=1, R=state[2]=1 → (0&1)|(1&1)=1  (vehicle arrives)
          i=2: C=1, L=state[1]=0, R=state[3]=0 → (1&0)|(0&0)=0  (vehicle moves)
          i=3: C=0, L=state[2]=1, R=state[0]=1 → (0&1)|(1&1)=1  (vehicle arrives)
          → [0, 1, 0, 1]
        Applying step() again returns to [1, 0, 1, 0] (period 2).
        """
        state = _s([1, 0, 1, 0])
        after = step(state, periodic=True)
        expected = _s([0, 1, 0, 1])
        np.testing.assert_array_equal(after, expected)
        # Period-2: a second step returns to the original.
        after2 = step(after, periodic=True)
        np.testing.assert_array_equal(after2, state)

    # -----------------------------------------------------------------------
    # 1e. Two consecutive vehicles: the rear one is blocked.
    # -----------------------------------------------------------------------
    def test_two_consecutive_vehicles(self):
        """
        [0, 1, 1, 0, 0] → [0, 1, 0, 1, 0]
        Leading vehicle (cell 2) moves to cell 3; rear vehicle (cell 1)
        is blocked because cell 2 was occupied (read from snapshot).

        Hand-check with new_C = (C&R) | (L&~C):
          i=0: C=0, L=state[4]=0, R=state[1]=1 → (0&1)|(0&1)=0
          i=1: C=1, L=state[0]=0, R=state[2]=1 → (1&1)|(0&0)=1  (blocked)
          i=2: C=1, L=state[1]=1, R=state[3]=0 → (1&0)|(1&0)=0  (moves right)
          i=3: C=0, L=state[2]=1, R=state[4]=0 → (0&0)|(1&1)=1  (receives vehicle)
          i=4: C=0, L=state[3]=0, R=state[0]=0 → (0&0)|(0&1)=0
          → [0, 1, 0, 1, 0]
        """
        state = _s([0, 1, 1, 0, 0])
        after = step(state, periodic=True)
        expected = _s([0, 1, 0, 1, 0])
        np.testing.assert_array_equal(after, expected)

    # -----------------------------------------------------------------------
    # 1f. Open boundary: vehicle exits at right, nothing enters from left.
    # -----------------------------------------------------------------------
    def test_open_boundary_vehicle_exits(self):
        """Vehicle at rightmost cell moves out (vanishes) under open boundary."""
        state = _s([0, 0, 0, 0, 1])
        after = step(state, periodic=False)
        # i=4: C=1, L=state[3]=0, R=ghost=0 → (1&0)|(0&0)=0 (vehicle leaves)
        expected = _s([0, 0, 0, 0, 0])
        np.testing.assert_array_equal(after, expected)

    def test_open_boundary_no_ghost_entry(self):
        """No vehicle enters from the left ghost cell under open boundary."""
        state = _s([0, 0, 0, 0, 0])
        after = step(state, periodic=False)
        np.testing.assert_array_equal(after, state)


# ===========================================================================
# 2. THE critical test: simultaneous vs. sequential update.
#
# This test is specifically designed so that a sequential (left-to-right)
# update gives a DIFFERENT result from the correct synchronous update.
# If this test passes, the implementation is synchronous.
# ===========================================================================

class TestSynchronousVsSequential:
    """
    Two distinguishing scenarios:

    Scenario A: state = [1, 0, 0, 0] (one vehicle at cell 0, periodic).

    Correct synchronous (snapshot of [1,0,0,0]):
      i=0: C=1, L=0, R=0 → (1&0)|(0&0)=0
      i=1: C=0, L=1, R=0 → (0&0)|(1&1)=1
      i=2: C=0, L=0, R=0 → 0
      i=3: C=0, L=0, R=1 → (0&1)|(0&1)=0
      Result: [0, 1, 0, 0]

    Incorrect sequential (update in place, left to right):
      i=0: update → cell 0 becomes 0 (vehicle "leaves")
      i=1: reads new[0]=0 as left neighbour → no vehicle arrives → stays 0
      i=2,3: all zeros
      Result: [0, 0, 0, 0]  ← vehicle vanishes — WRONG.

    Scenario B: state = [1, 1, 0, 1] (periodic).

    Correct synchronous:
      i=0: C=1, L=1, R=1 → (1&1)|(1&0)=1
      i=1: C=1, L=1, R=0 → (1&0)|(1&0)=0 (vehicle moves)
      i=2: C=0, L=1, R=1 → (0&1)|(1&1)=1 (vehicle arrives)
      i=3: C=1, L=0, R=state[0]=1 → (1&1)|(0&0)=1 (blocked)
      Result: [1, 0, 1, 1]

    Incorrect sequential:
      i=0: C=1,L=state[3]=1,R=state[1]=1 → 1, state[0]=1
      i=1: C=1,L=state[0]=1,R=state[2]=0 → 0, state[1]=0
      i=2: C=0,L=new[1]=0,R=state[3]=1 → (0&1)|(0&1)=0  ← WRONG (correct is 1)
      i=3: stays 1
      Result: [1, 0, 0, 1]  ← different from synchronous.
    """

    def test_single_vehicle_synchronous(self):
        """Lone vehicle must move from cell 0 → cell 1, not vanish."""
        state = _s([1, 0, 0, 0])
        after = step(state, periodic=True)
        expected = _s([0, 1, 0, 0])
        np.testing.assert_array_equal(after, expected,
            err_msg="Vehicle vanished — likely sequential update bug.")

    def test_multi_vehicle_synchronous(self):
        """
        [1, 1, 0, 1] → [1, 0, 1, 1] synchronously.
        Sequential update gives [1, 0, 0, 1] — different result.
        """
        state = _s([1, 1, 0, 1])
        after = step(state, periodic=True)
        expected = _s([1, 0, 1, 1])
        np.testing.assert_array_equal(after, expected,
            err_msg="Result matches sequential update, not synchronous.")

    def test_state_not_mutated(self):
        """step() must return a NEW array and not mutate the input."""
        state = _s([1, 0, 1, 0, 0])
        original = state.copy()
        _ = step(state, periodic=True)
        np.testing.assert_array_equal(state, original,
            err_msg="step() mutated the input state array.")


# ===========================================================================
# 3. Properties of random_initial_state
# ===========================================================================

class TestRandomInitialState:

    def test_exact_vehicle_count(self):
        """Exact number of vehicles placed (no off-by-one from float density)."""
        rng = np.random.default_rng(42)
        for density in [0.1, 0.3, 0.5, 0.7, 0.9]:
            state = random_initial_state(200, density, rng)
            expected = round(density * 200)
            assert int(state.sum()) == expected, (
                f"density={density}: got {state.sum()} vehicles, expected {expected}"
            )

    def test_values_binary(self):
        """All cell values are 0 or 1."""
        rng = np.random.default_rng(42)
        state = random_initial_state(100, 0.4, rng)
        assert set(np.unique(state)).issubset({0, 1})

    def test_density_zero(self):
        rng = np.random.default_rng(0)
        state = random_initial_state(100, 0.0, rng)
        assert state.sum() == 0

    def test_density_one(self):
        rng = np.random.default_rng(0)
        state = random_initial_state(100, 1.0, rng)
        assert state.sum() == 100

    def test_different_seeds_different_state(self):
        """Different seeds produce different initial conditions (w.h.p.)."""
        s1 = random_initial_state(100, 0.5, np.random.default_rng(1))
        s2 = random_initial_state(100, 0.5, np.random.default_rng(2))
        # The probability of them being equal is astronomically small.
        assert not np.array_equal(s1, s2)


# ===========================================================================
# 4. Flow-density correctness: steady-state flow = min(ρ, 1-ρ) exactly.
#    This is the hard mathematical correctness target from plan.md §6.
# ===========================================================================

class TestFlowDensityCorrectness:

    ROAD_LEN = 500
    WARMUP   = 1000   # steps discarded before measuring
    MEASURE  = 500    # steps over which flow is measured

    def _steady_flow(self, density: float, seed: int) -> tuple[float, float]:
        rng = np.random.default_rng(seed)
        state = random_initial_state(self.ROAD_LEN, density, rng)
        state = run(state, self.WARMUP, periodic=True)
        history = run_collect(state, self.MEASURE, periodic=True)
        mean_f, std_f = measure_flow(history)
        return mean_f, std_f

    @pytest.mark.parametrize("density", [0.1, 0.2, 0.3, 0.4, 0.5,
                                          0.6, 0.7, 0.8, 0.9])
    def test_flow_matches_theoretical(self, density):
        """Measured flow must be within 1e-6 of min(ρ, 1-ρ)."""
        mean_f, _ = self._steady_flow(density, seed=0)
        theoretical = min(density, 1 - density)
        assert abs(mean_f - theoretical) < 1e-6, (
            f"ρ={density}: measured={mean_f:.8f}, theory={theoretical:.8f}, "
            f"error={abs(mean_f-theoretical):.2e}"
        )

    @pytest.mark.parametrize("density", [0.1, 0.3, 0.5, 0.7, 0.9])
    def test_zero_variance_at_steady_state(self, density):
        """
        Rule 184 is deterministic → std of flow must be exactly 0 at
        steady state (once the transient is gone).

        Tolerance: 1e-12 (numerical noise floor for int8 arrays).
        """
        _, std_f = self._steady_flow(density, seed=0)
        assert std_f < 1e-12, (
            f"ρ={density}: std_flow={std_f:.2e} (expected ~0 for deterministic Rule 184)"
        )

    @pytest.mark.parametrize("density", [0.2, 0.5, 0.8])
    def test_seed_independence(self, density):
        """
        Two different random seeds must converge to the same steady-state
        flow (same integer vehicle count, different initial arrangement).
        """
        f1, _ = self._steady_flow(density, seed=100)
        f2, _ = self._steady_flow(density, seed=999)
        assert abs(f1 - f2) < 1e-9, (
            f"ρ={density}: seed 100 flow={f1:.8f}, seed 999 flow={f2:.8f}"
        )


# ===========================================================================
# 5. run() and run_collect() sanity checks
# ===========================================================================

class TestRunFunctions:

    def test_run_returns_same_shape(self):
        state = _s([1, 0, 1, 0, 0, 1])
        out = run(state, 10)
        assert out.shape == state.shape

    def test_run_collect_shape(self):
        state = _s([1, 0, 0, 1, 0])
        hist = run_collect(state, 5)
        assert hist.shape == (6, 5)   # (n_steps+1, N)

    def test_run_collect_first_row_is_initial(self):
        state = _s([1, 0, 0, 1, 0])
        hist = run_collect(state, 5)
        np.testing.assert_array_equal(hist[0], state)

    def test_run_collect_conserves_vehicles_periodic(self):
        """Periodic boundary: vehicle count is conserved exactly."""
        rng = np.random.default_rng(7)
        state = random_initial_state(100, 0.4, rng)
        hist = run_collect(state, 200, periodic=True)
        counts = hist.sum(axis=1)
        assert np.all(counts == counts[0]), (
            "Vehicle count not conserved under periodic BC."
        )
