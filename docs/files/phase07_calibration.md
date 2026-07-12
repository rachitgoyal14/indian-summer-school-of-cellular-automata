# PHASE 7 — Calibration

## Before you start
Follow `00_START_HERE.md`. Requires Phase 6's `Collector`, `density_flow.py`
(`flow_density_table`), and `trajectory_export.py` passing all tests, and a field (or
synthetic-fallback) dataset from Phase 0 in `data/processed/`.

## Goal of this phase
Tune the per-mode behavioral parameters (the ones currently sitting as placeholders in
`configs/intersection_default.yaml`: `max_speed`, `max_accel`, `p_slowdown`/randomization
prob, `lane_change_prob`, `position_preference`, IZOI-related deceleration rate, seepage
safety margins/advance rate — roughly the "11 per-mode parameters" plan.md's Table 2
references) against field flow/density data, using a two-stage global→local optimizer.
Reference plan.md §3 Phase 7, Eq 16.

## Steps

### 1. Install optimizer deps
Add `pymoo` and confirm `scipy` is present (already installed Phase 0) to `requirements.txt`.

### 2. `src/calibration/objective.py`
- `calibration_objective(params: dict, config_template: dict, field_flow_density: pd.DataFrame, rng_seed: int) -> float`:
  1. Merge `params` into a copy of `config_template` (do not mutate the template).
  2. Run `run_full_intersection` (Phase 6's collector-backed version) with this merged config
     for a duration matching the field data's time window (use whatever duration the field CSV
     actually covers — read it, don't assume).
  3. Compute simulated flow/density via `flow_density_table` at the SAME 5-minute bin
     resolution as the field data.
  4. Return the sum-of-squared-relative-error per Eq 16:
     `sum over bins of ((field_flow - sim_flow)/field_flow)^2 + ((field_density - sim_density)/field_density)^2`
     (guard against division by zero bins with a small epsilon or bin-exclusion — document
     whichever you choose).
- Write `tests/test_objective.py`: assert that running the objective with the field data
  compared against itself (i.e., a "simulated" dataset that's actually just the field data
  re-fed through the metrics pipeline) returns ~0. This proves the objective function's
  plumbing is correct independent of the simulator's actual behavioral accuracy.

### 3. `src/calibration/optimizer.py`
- Define the parameter search space explicitly as a dict of `(name, mode, lower_bound, upper_bound)`
  tuples — enumerate all ~11 parameters × 4 modes = ~44 dimensions per plan.md, but ALLOW a
  `reduced_mode: bool` flag that calibrates only a smaller subset first (e.g. just
  `max_speed`, `p_slowdown`, `lane_change_prob` × 4 modes = 12 dimensions) as a faster/cheaper
  first pass — implement this flag, don't just mention it, since a full 44-dim GA run may be
  too slow for a first working version.
- **Stage 1 (global)**: use `pymoo`'s NSGA-II (or single-objective GA if you collapse Eq 16 to
  one scalar, which is simpler and acceptable here — document the simplification from the
  paper's true multi-objective `gamultiobj` to a single-objective GA) over the bounded search
  space, population ~30-50, generations ~20-30 for the reduced parameter set (scale down
  further if runs are too slow — log wall-clock time per generation and adapt).
- **Stage 2 (local refinement)**: take Stage 1's best result, run `scipy.optimize.minimize`
  (Nelder-Mead, since the objective is non-smooth/stochastic) starting from that point for
  local polish.
- `run_calibration(config_template, field_data_path, reduced_mode: bool = True) -> dict`:
  orchestrates both stages, returns the best parameter dict, and writes a convergence log
  (best objective value per generation) to `data/processed/calibration_convergence.csv`.

### 4. `scripts/run_calibration.py`
CLI entry point: loads config + field data, calls `run_calibration`, writes the calibrated
parameters to a NEW config file `configs/intersection_calibrated.yaml` (never overwrite
`intersection_default.yaml` — keep the original placeholders around for comparison/debugging).

## Validation
- Plot `data/processed/calibration_convergence.csv` (best objective vs. generation) —
  save to `notebooks/figures/phase7_calibration_convergence.png`; it must show a
  non-increasing (plateauing) trend, not noise with no downward trend (if it's just noise,
  something in the objective or optimizer wiring is broken).
- Sanity-check calibrated parameters land in "physically reasonable" ranges (probabilities in
  [0,1], speeds/accelerations positive and mode-ordered consistently with Phase 2's capacity
  ordering result) — print a before/after (`intersection_default.yaml` vs
  `intersection_calibrated.yaml`) comparison table to `PHASE_REPORT.md`.

## Acceptance criteria
- [ ] `pytest -q` passes, including `test_objective.py`'s near-zero self-comparison check.
- [ ] `phase7_calibration_convergence.png` shows a plateauing convergence curve.
- [ ] `configs/intersection_calibrated.yaml` exists with all calibrated values in physically
      sane ranges (explicitly listed and checked in `PHASE_REPORT.md`).
- [ ] `PHASE_REPORT.md` updated with `## Phase 7` section: which parameters were calibrated
      (full 44-dim vs reduced set — state which), wall-clock time taken, and the
      single-objective-GA-vs-paper's-multi-objective-gamultiobj simplification explicitly
      noted (per plan.md §11 risk #3 — do not claim exact parameter-value replication).
- [ ] Git commit made.

## Explicitly out of scope
Formal statistical validation (GEH, Theil's U, etc.) against a held-out validation split is
Phase 8, not this phase — this phase only fits parameters against the calibration split.
