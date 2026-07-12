# PHASE 3 — Signal State Machine + IZOI (No Seepage Yet)

## Before you start
Follow `00_START_HERE.md`. Requires Phase 2's multi-mode midblock engine (`gaps.py`,
`lane_change.py`, `motion.py`, multimode `sim_loop.py`) passing all tests.

## Goal of this phase
Add a fixed-time traffic signal and the Influence Zone of Intersection (IZOI) behavior
switch to a **single approach leg** (still not the full 4-leg intersection — that's Phase 4).
Reference plan.md §3 Phase 3, Algorithm 2, Eq 3, Table 1 (IZOI ~99-214m depending on mode,
literature placeholder is fine here per plan.md §11 risk #2).

## Steps

### 1. `src/intersection/signal.py`
- A `Signal` class with `cycle_length_s`, `green_s`, `red_s` (green_s + red_s = cycle_length_s;
  validate this in `__init__`, raise `ValueError` if not), and a `phase_offset_s` for
  multi-approach use later.
- Method `state_at(t_s: float) -> Literal["green", "red"]` — pure function of time, no
  internal mutable state beyond the fixed config (this makes it trivially testable and
  reusable across multiple legs with different offsets in Phase 4).
- Add to `configs/intersection_default.yaml`:
  ```yaml
  signal:
    cycle_length_s: 90
    green_s: 45
    red_s: 45
  ```
- `tests/test_signal.py`: assert `state_at` returns correct green/red across at least one full
  cycle including boundary timestamps (t=0, t=green_s exactly, t=cycle_length_s).

### 2. `src/intersection/izoi.py`
- Add `izoi_distance_m` per mode to config, using plan.md Table 1's cited literature range
  (~99-214 m) — pick reasonable mode-ordered placeholders (two_wheeler shortest reaction/IZOI,
  bus longest) and clearly comment in the YAML that these are literature placeholders pending
  field-data calibration, per plan.md §11 risk #2.
  ```yaml
  izoi_distance_m:
    two_wheeler: 100
    three_wheeler: 120
    car: 150
    bus: 200
  ```
- Function `is_in_izoi(vehicle, stop_line_position_cells, izoi_distance_cells) -> bool`.
- Function `izoi_behavior(vehicle, signal_state, field_decel_rate, gaps) -> ...`: implement
  Algorithm 2's exact branching —
  - if NOT in IZOI: return "midblock" (i.e., do nothing different, Phase 2 rules apply as-is).
  - if in IZOI and signal is RED: decelerate at `field_decel_rate` (config value, e.g.
    `izoi_deceleration_rate: 2.0  # cells/step^2`, add to YAML) with NO randomization
    (this is the key difference from midblock rules — explicitly skip the `randomize` step
    for any vehicle in this state), continuing to reduce speed until stopped at/behind the
    vehicle ahead or the stop line, whichever is closer.
  - if in IZOI and signal is GREEN: continue as midblock (normal Phase 2 rules), UNLESS a
    stopped queue still exists ahead (i.e., discharge is naturally gated by the front-gap
    logic you already have from Phase 2 — you do not need new logic for this case, the
    existing `decelerate_for_gap` handles it once the lead vehicle starts moving).
  Write `tests/test_izoi.py` covering all 3 branches explicitly with hand-constructed
  single/few-vehicle fixtures, including a case that proves randomization is skipped inside
  IZOI+red (e.g. run the deceleration step many times with a fixed rng seed sequence and
  assert speed decreases monotonically with no upward "randomization" blip).

### 3. Update `src/sim/sim_loop.py`
Add `run_single_leg_with_signal(config, duration_s, mode_mix, rng) -> pd.DataFrame` that
wires: generate → for each vehicle, check `is_in_izoi` → branch via `izoi_behavior` OR
Phase-2 midblock pipeline → update position. A vehicle that reaches speed 0 at/behind the
stop line while signal is red must remain stationary (not drift) until conditions allow motion.

## Validation
`notebooks/figures/phase3_queue_formation.png`: plot a space-time (x vs t) diagram of ~2-3
signal cycles for a single approach with continuous vehicle arrivals. **Required visual
result**: a clearly visible sawtooth queue — vehicles pile up behind the stop line during red
(forming a growing queue with roughly-parallel trajectory lines), then discharge in order
during green (queue length shrinks, trajectories fan out with increasing slope/speed).

Also compute and report (not necessarily unit-tested to a precise target, since you don't
have field data yet, but must be printed/logged): approximate saturation flow rate (veh/hr)
during the green phase, using the discharge headway of the first ~10 queued vehicles after
green starts. This becomes a sanity-check baseline for Phase 9's delay module.

## Acceptance criteria
- [ ] `pytest -q` passes, including Phase 1-2 regression tests plus new signal/IZOI tests.
- [ ] `phase3_queue_formation.png` shows visible queue buildup on red and discharge on green
      (not a flat/uniform trajectory pattern — if you see that, the IZOI+red branch is
      probably not being triggered; check `is_in_izoi` boundary logic first).
- [ ] No vehicle passes through the stop line during red (add explicit
      `tests/test_no_red_light_running.py`).
- [ ] `PHASE_REPORT.md` updated with `## Phase 3` section including the queue plot reference,
      the computed saturation flow estimate, and explicit note that IZOI distances are
      literature placeholders (per plan.md §11 risk #2), not yet field-calibrated.
- [ ] Git commit made.

## Explicitly out of scope
Still single leg only — no 4-leg intersection, no turning movements, no seepage.
