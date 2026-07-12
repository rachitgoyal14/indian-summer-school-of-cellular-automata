# PHASE 9 — Delay Module + Manual Benchmarking

## Before you start
Follow `00_START_HERE.md`. Requires Phase 8's validation suite passing and
`data/processed/validation_results.csv` existing.

## Goal of this phase
Compute average intersection delay directly from simulation output, and cross-check it
against at least 2 closed-form highway-capacity-manual delay formulas, reproducing a
chart in the style of plan.md's reference to the paper's Figure 17 / Table 5. Reference
plan.md §3 Phase 9.

## Steps

### 1. `src/delay/simulated_delay.py`
- `compute_vehicle_delay(vehicle_trajectory: pd.DataFrame, free_flow_speed_mps: float) -> float`:
  for ONE vehicle's full trajectory (from Collector output, filtered to one `vehicle_id`),
  compute delay as the difference between (a) actual travel time through the
  observation/IZOI section and (b) the travel time it WOULD have taken at
  `free_flow_speed_mps` over the same distance. This captures both stopped delay and
  acceleration/deceleration delay in one measure, consistent with plan.md's description
  ("stopped + acceleration/deceleration delay per vehicle, aggregated").
- `average_intersection_delay(collector_df, free_flow_speed_mps_by_mode: dict) -> dict`:
  groups by `leg_origin` (and optionally by mode), applies `compute_vehicle_delay` per
  vehicle, and returns average delay per leg and overall, in seconds/vehicle.
- `tests/test_simulated_delay.py`: hand-constructed fixture — one vehicle trajectory that
  travels at exactly free-flow speed throughout (delay should be ~0), and one that stops for a
  known duration (delay should equal the known stop duration within a small tolerance).

### 2. `src/delay/manuals/` — implement at least 2 of these 3 as standalone formula modules,
   each taking the SAME input parameters (demand flow veh/hr, capacity veh/hr, green ratio
   g/C, cycle length C) so they're directly comparable:
   - `indo_hcm.py`: `indo_hcm_delay(demand_veh_hr, capacity_veh_hr, green_ratio, cycle_s) -> float`
     — implement the Indo-HCM (2017) uniform + incremental delay formula (standard
     Webster-family structure: `d = d1*PF + d2`, where `d1` is uniform delay from
     `0.5*C*(1-g/C)^2 / (1 - min(1, X)*g/C)`, `X` = demand/capacity ratio, and `d2` is an
     incremental term `900*T*[(X-1) + sqrt((X-1)^2 + (8*k*I*X)/(capacity*T))]` with standard
     default `k=0.5, I=1.0, T=0.25hr` unless you have better values — clearly comment which
     constants are Indo-HCM defaults vs. generic HCM defaults, since these tables sometimes
     differ and you should note you're using the widely-published generic form since you don't
     have the Indo-HCM manual text itself).
   - `indonesian_hcm.py`: simpler Webster-based formula (`indonesian_hcm_delay(...)`, same
     signature) — this is plan.md's suggested "simplest closed-form" option, implement
     Webster's original average delay formula:
     `d = C*(1-g/C)^2 / (2*(1 - (g/C)*X)) - 0.65*(C/X^2)^(1/3) * X^(2+5*(g/C))` (Webster's full
     formula including the empirical correction term) or, if you prefer, Webster's simpler
     uncorrected first term only — pick one, document which, and be consistent.
   - `hcm2010.py` (optional third, only if time permits): US HCM 2010 signalized delay formula
     — same `d1*PF + d2` structure as Indo-HCM but with HCM-2010-specific default
     constants; skip if this starts duplicating `indo_hcm.py` too closely — 2 manuals is the
     Phase acceptance minimum per plan.md, not 3.
   Write `tests/test_manuals.py`: for each implemented manual, assert delay increases
   monotonically as `demand_veh_hr` increases toward `capacity_veh_hr` (holding other params
   fixed) — this is a basic sanity property any correct delay formula must satisfy, and a
   cheap way to catch a transcription bug in the formula.

### 3. `scripts/run_delay_comparison.py`
- Run (or reuse Phase 8's) a full-intersection simulation with the calibrated config.
- Compute `average_intersection_delay` from its output.
- Feed the SAME demand/capacity/green-ratio parameters (derived from the simulation's actual
  config and observed saturation flow — reuse Phase 3's saturation flow estimate logic) into
  each implemented manual formula.
- Produce a grouped bar chart: simulated delay vs. each manual's delay estimate, per leg (or
  aggregate if per-leg is too noisy) — save to `notebooks/figures/phase9_delay_comparison.png`
  in the style of plan.md's Figure-17 reference.
- Save the underlying numbers to `data/processed/delay_comparison.csv`.

## Acceptance criteria
- [ ] `pytest -q` passes, including `test_simulated_delay.py` and `test_manuals.py`.
- [ ] At least 2 manual formula modules implemented and passing their monotonicity tests.
- [ ] `phase9_delay_comparison.png` produced, showing simulated delay alongside ≥2 manual
      estimates.
- [ ] `PHASE_REPORT.md` updated with `## Phase 9` section: the actual delay numbers obtained,
      which manuals were implemented, which constants were assumed/defaulted (flagged
      explicitly since you don't have the manuals' original tables), and an honest discussion
      of how close simulated vs. manual estimates are and plausible reasons for any large gap
      (e.g. placeholder/synthetic calibration data, simplified conflict rules from Phase 4).
- [ ] Git commit made.

## Explicitly out of scope
No new simulator behavior — this phase only consumes existing simulation output and adds
formula/analysis code.
