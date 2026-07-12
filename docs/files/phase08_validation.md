# PHASE 8 — Validation Suite

## Before you start
Follow `00_START_HERE.md`. Requires Phase 7's `configs/intersection_calibrated.yaml` and
`run_calibration.py` output to exist and pass tests.

## Goal of this phase
Implement the paper's macroscopic and microscopic validation statistics as reusable, unit-
tested pure functions, run them on a held-out validation split (different time window/day
than what Phase 7 calibrated against), and report against the paper's own target thresholds.
Reference plan.md §3 Phase 8, Eq 17-23, and §6 (calibration/validation split methodology).

## Steps

### 1. Prepare the validation split
- If using synthetic data (Phase 0 fallback still active): generate a SECOND synthetic
  dataset with a different `random_seed` (document this seed) to stand in for "a different
  day/site," per plan.md §6 step 1's calibration/validation split logic. If real Kanagaraj
  data was successfully downloaded, split it into two non-overlapping time windows instead
  (e.g. the 2:45-3:00 PM file for calibration, the 3:00-3:15 PM file for validation — this
  matches the two files' natural split).
- Document explicitly in `PHASE_REPORT.md` which split strategy was used.

### 2. `src/metrics/stats.py` (new, standalone — plan.md explicitly calls these out as reusable
outside this project too, so write them as pure functions with no simulator dependencies)
Implement, each as its own function with its own docstring citing the Eq number:
- `geh(observed: np.ndarray, simulated: np.ndarray) -> np.ndarray` — Eq 23:
  `sqrt(2*(sim-obs)^2 / (sim+obs))` elementwise.
- `rmse(observed, simulated) -> float` — Eq 21.
- `rmspe(observed, simulated) -> float` — Eq 22 (percentage version of RMSE).
- `theils_u_decomposition(observed, simulated) -> dict` — Eq 17-20: returns
  `{"U": ..., "U_bias": ..., "U_variance": ..., "U_covariance": ...}` where the three
  components sum to 1 (Theil's inequality proportions) — implement this decomposition exactly
  per the standard formulas (bias proportion = (mean_diff)^2/MSE, variance proportion =
  (std_obs - std_sim)^2/MSE, covariance proportion = 2(1-r)*std_obs*std_sim/MSE where r is the
  correlation coefficient) and add an assertion/test that the three components sum to
  ~1.0 (within floating point tolerance) as a self-check.
- `two_sample_ttest_unequal_var(observed_flows, simulated_flows) -> tuple[float, float]`
  (t-statistic, p-value) — thin wrapper around `scipy.stats.ttest_ind(..., equal_var=False)`,
  written as its own named function so calibration/validation scripts don't call scipy
  directly (keeps the stats module the single source of truth).

Write `tests/test_stats.py` with hand-computable fixtures for EVERY function above (small
arrays, e.g. 4-5 numbers, where you compute the expected GEH/RMSE/RMSPE/Theil's-U by hand or
with an independent reference calculation and assert your function matches to a tight
tolerance). Also test the edge case `observed == simulated` exactly, which should give GEH≈0,
RMSE=0, RMSPE=0, Theil's U=0.

### 3. `src/metrics/validation_macro.py`
- `macro_validation_report(field_df, sim_df, window_s) -> dict`: uses `flow_density_table`
  (Phase 6) on both field and sim data, aligns them by time window, runs
  `two_sample_ttest_unequal_var` on the flow series, and returns a dict with the t-test
  result plus a flow-density overlay plot (matplotlib) saved to
  `notebooks/figures/phase8_macro_fd_overlay.png`.

### 4. `src/metrics/validation_micro.py`
- `micro_validation_report(field_trajectory_df, sim_trajectory_df) -> dict`: aligns
  observed vs simulated speed and headway distributions (bin/interpolate to comparable
  sampling if needed — document your alignment method explicitly, this is a common source of
  silent bugs), computes GEH on volumes, RMSE/RMSPE on speed and headway, and the full Theil's
  U decomposition on speed. Returns a dict of all these values AND saves comparison plots
  (`notebooks/figures/phase8_micro_speed_comparison.png`,
  `notebooks/figures/phase8_micro_headway_comparison.png`).

### 5. `scripts/run_validation.py`
CLI entry point that loads the calibrated config, runs a fresh simulation (NEW random seed,
different from calibration's seed — this matters, per plan.md §6 step 4) over the validation
split's conditions, and prints/saves a combined results table mirroring the paper's Table 3-4
structure to `data/processed/validation_results.csv` and a human-readable summary appended to
`PHASE_REPORT.md`.

## Acceptance criteria
- [ ] `pytest -q` passes, including all `test_stats.py` hand-computed fixtures.
- [ ] `validation_results.csv` contains GEH, Theil's U (+ 3 sub-components summing to ~1),
      RMSE, RMSPE, and t-test p-value.
- [ ] `phase8_macro_fd_overlay.png` and the two micro comparison plots are produced.
- [ ] `PHASE_REPORT.md` updated with `## Phase 8` section reporting the actual numbers
      obtained and an HONEST comparison against the paper's target thresholds (GEH < 5,
      Theil's U < 20%) — if targets aren't met, say so plainly and note it's expected given
      placeholder/synthetic data rather than paper-exact field data (do not fabricate passing
      numbers).
- [ ] Git commit made.

## Explicitly out of scope
Delay/manual-formula comparison is Phase 9. This phase is flow/density/speed/headway/volume
statistics only.
