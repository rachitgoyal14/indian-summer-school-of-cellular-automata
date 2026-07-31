# PHASE 1 — Core Rule 184 Engine (No Graphics)

## Before you start
Read `plan.md` in full first, especially Section 4 (Rule 184's exact correctness target) and Section 7 risk #1 (synchronous vs. sequential update). This phase has zero graphics — pure array logic, validated mathematically.

## Goal of this phase
Implement elementary cellular automaton **Rule 184** for a single one-way lane, with no junctions, no disruptions, no rendering. Prove it reproduces the exact known flow-density relationship before anything else is built.

## What Rule 184 actually is
A 1D array of cells, each either 0 (empty) or 1 (occupied by a car). Every timestep, **simultaneously** (not one at a time): a car at position *i* moves to position *i+1* if and only if cell *i+1* is currently empty (in the *previous* timestep's state). If cell *i+1* is occupied, the car at *i* stays put. This is applied to every cell at once, from a single snapshot of the previous state — not sequentially left-to-right or right-to-left, which would silently change the dynamics and break the exact solution below.

## Steps

### 1. `src/core/cell.py`
- A simple representation of a road: a 1D NumPy array of 0s and 1s, length `road_length_cells`.
- Function `random_initial_state(length: int, density: float, rng: np.random.Generator) -> np.ndarray`: returns a random 0/1 array with approximately `density` fraction of cells occupied (exact count, not just probability — round to nearest integer number of cars and place them at random positions, so density is exact for reproducible testing).

### 2. `src/core/rule184.py`
- `step(state: np.ndarray, periodic: bool = True) -> np.ndarray`: applies one synchronous Rule 184 update and returns the NEW array (do not mutate the input array in place — this is what guarantees correct simultaneous update; compute the new state fully from a read-only copy of the old state before returning it).
- Support both **periodic boundary** (a car at the last cell wraps around to cell 0 if empty) and **open boundary** (a car at the last cell simply exits/disappears, and no new car enters) — periodic is what you'll use for the Phase 1 correctness check below; open boundary will matter for later phases with real road segments.
- Write `tests/test_rule184.py` with small, hand-computable fixtures: e.g. state `[1,1,0,0]` (periodic) → next state should be `[0,1,1,0]` (compute this by hand and confirm your intuition, then assert it). Include a fixture that specifically tests the simultaneous-update property: a state where sequential (wrong) update would give a different answer than simultaneous (correct) update, and assert your function gives the correct simultaneous result.

### 3. `src/analytics/density.py` (minimal, just what's needed for this phase's check)
- `flow_at_step(prev_state: np.ndarray, next_state: np.ndarray) -> float`: fraction of cars that actually moved this step (i.e., fraction of cells where a car was at position *i* in `prev_state` and is now at *i+1* in `next_state`). This is "flow" for Rule 184 — the fraction of cars successfully advancing per timestep.
- `density_of(state: np.ndarray) -> float`: fraction of occupied cells.

## Validation — this is the acceptance criterion, not optional
Rule 184 under periodic boundaries has an **exact, known solution**: for a system that has run long enough to reach steady state, average flow = min(ρ, 1-ρ), where ρ is density. This is a straight-line-up-then-straight-line-down triangle, peaking exactly at ρ=0.5, flow=0.5 — and unlike NaSch-style models, there is no randomness in the answer once you're at steady state, so this should match almost exactly, not just "roughly triangular."

Build `notebooks/phase1_rule184_fd_check.py` (or `.ipynb`) that:
1. For at least 15-20 density values evenly spread from ρ=0.05 to ρ=0.95, initializes a periodic-boundary road (at least 500 cells long, to reduce finite-size noise) at that density.
2. Runs several hundred warm-up steps (to reach steady state — Rule 184 can take a little time to settle from a random initial condition into its steady flow pattern).
3. Measures average flow over a further measurement window (average `flow_at_step` across many subsequent steps).
4. Plots measured flow vs. density, and overlays the theoretical curve min(ρ, 1-ρ) as a reference line on the same plot.

**Required result:** your measured points should sit almost exactly on the theoretical triangle line — small deviations from finite road length or measurement noise are fine, but a *shape* mismatch (not peaking at 0.5, not symmetric, not linear on each side) means something is wrong in your Rule 184 implementation, most likely the synchronous-update requirement from Section 7 risk #1. Do not proceed to Phase 2 until this matches closely.

## Acceptance criteria
- [ ] `pytest -q` passes, including the simultaneous-vs-sequential fixture test.
- [ ] The flow-density plot's measured points closely track the theoretical min(ρ, 1-ρ) triangle across the full density range tested.
- [ ] `PHASE_REPORT.md` created with a `## Phase 1` section documenting the check above, with the plot embedded/referenced, and explicit confirmation that the update is synchronous (read from an old-state snapshot, write to a new array).
- [ ] Git commit made.

## Explicitly out of scope
No graphics, no junctions, no disruptions, no open-boundary vehicle generation logic yet — pure periodic-boundary Rule 184 correctness only.
