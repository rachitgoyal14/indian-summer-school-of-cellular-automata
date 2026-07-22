# PHASE 6 — Data Collection & Metrics Layer

## Before you start
Follow `00_START_HERE.md`. Requires Phase 5's seepage-enabled full intersection passing all
tests. This phase does NOT add new vehicle-behavior logic — it formalizes the logging/metrics
layer that calibration (Phase 7) and validation (Phase 8) will consume. Reference plan.md §3
Phase 6, Eq 6-15.

## Why this phase exists as its own step
Phases 1-5 each already log a DataFrame from their own `sim_loop.py` functions, but each
phase invented its own ad-hoc column set. This phase's job is to (a) consolidate into ONE
canonical collector interface every later phase depends on, and (b) implement the
cell-occupancy-based density/flow formulas (Eq 6-15) properly, replacing Phase 1's simplified
version.

## Steps

### 1. `src/sim/collector.py` (new, canonical)
- `Collector` class with a `.record(t_s, vehicles, intersection_state)` method called once per
  simulation timestep, and a `.to_dataframe() -> pd.DataFrame` method. It must capture, per
  vehicle per timestep, the full canonical column set:
  ```
  time_s, vehicle_id, mode, leg_origin, leg_destination, turn,
  position_cells, lateral_position_cells, speed_cells_per_step,
  accel_cells_per_step2, in_izoi: bool, signal_state, seepage_action
  ```
  (`accel_cells_per_step2` = speed this step minus speed last step, computed inside the
  collector by diffing consecutive records per vehicle — do not require `sim_loop.py` to
  track this separately.)
- Refactor `src/sim/sim_loop.py`'s `run_full_intersection` (from Phase 5) to use this
  `Collector` instead of its own ad-hoc DataFrame building. **This is a refactor, not a
  rewrite** — the simulation behavior/results must be identical before and after; prove this
  with a regression test (below).
- `tests/test_collector_regression.py`: run `run_full_intersection` with a fixed seed both
  via the OLD Phase-5 logging path (if you kept a copy) and the NEW collector, and assert key
  aggregate stats (vehicle count, final positions) match. If you didn't keep a copy of the old
  path, instead assert the new collector's output satisfies all the Phase 4/5 collision and
  eligibility invariants already tested — i.e., re-run those same invariant tests against
  collector output as an equivalent regression check.

### 2. `src/metrics/density_flow.py` (formalize Eq 6-15)
Replace/extend Phase 1's simplified `flow_density_from_log` with the paper's cell-occupancy
method explicitly:
- `density_veh_per_km(occupied_cells: int, total_cells: int, avg_vehicle_footprint_cells: float, cell_length_m: float) -> float`
  per Eq 6-15's occupied-cells-to-density conversion.
- `flow_veh_per_hr(crossings_in_window: int, window_s: int) -> float`.
- `flow_density_table(collector_df, road_geometry, window_s: int) -> pd.DataFrame` — the
  single function all later phases (calibration, validation) call, producing one row per
  time window with `time_window, mode, density_veh_per_km, flow_veh_per_hr`.
- **Critical bug-avoidance requirement (plan.md §11 risk #4)**: this function must import
  `cell_length_m`, `cell_width_m` from the SAME config object used everywhere else (grid,
  gaps, seepage) — add an explicit `tests/test_cell_size_consistency.py` that walks the
  config and every module that references cell size (`grid.py`, `gaps.py`, `seepage.py`,
  `density_flow.py`) and asserts they all read from the same config keys, not independently
  hardcoded values. Grep-based or import-based check is fine — the point is to catch drift
  early per the paper's explicit warning about this exact bug class.

### 3. `src/metrics/trajectory_export.py` (new, small)
- `export_trajectories(collector_df, out_path: str) -> None`: writes a clean, minimal
  trajectory CSV (`vehicle_id, mode, time_s, x_m, y_m, speed_mps`, converted from cells to
  meters using config cell sizes) to `data/processed/sim_trajectories_<scenario_name>.csv`.
  This format matches the field-data schema from Phase 0, so validation (Phase 8) can compare
  field vs. simulated trajectories using the exact same loading code.

## Validation
Run a ~30-minute simulated scenario end-to-end through the new collector, produce
`flow_density_table` output, and plot it (reuse the Phase 2 FD-by-mode plotting code, pointed
at the new metrics functions) to confirm the FD shape/ordering result from Phase 2 still
holds after the refactor. Save as `notebooks/figures/phase6_post_refactor_fd_check.png` —
this should look qualitatively the same as Phase 2's plot; if it doesn't, the refactor broke
something and must be fixed before proceeding.

## Acceptance criteria
- [ ] `pytest -q` passes, all prior phases' regression tests included, plus new collector and
      cell-size-consistency tests.
- [ ] `phase6_post_refactor_fd_check.png` qualitatively matches Phase 2's FD ordering result.
- [ ] `data/processed/sim_trajectories_<scenario_name>.csv` exists with the field-data-matching
      schema.
- [ ] `PHASE_REPORT.md` updated with `## Phase 6` section confirming the refactor didn't change
      simulation behavior (cite the regression test).
- [ ] Git commit made.

## Explicitly out of scope
No calibration optimization yet (Phase 7), no formal validation statistics yet (Phase 8) —
this phase only builds the plumbing those phases will consume.
