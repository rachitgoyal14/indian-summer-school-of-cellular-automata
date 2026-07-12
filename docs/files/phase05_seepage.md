# PHASE 5 — Seepage Behavior (Algorithm 3)

## Before you start
Follow `00_START_HERE.md`. Requires Phase 4's full intersection (`intersection.py`,
`routing.py`, 4-leg sim loop) passing all tests. This is the single most important novel
behavior in the whole replication — read plan.md's Algorithm 3, Fig 5, Fig 6, Fig 7, Eq 4-5
description carefully (in plan.md §2 table and §4 checklist) before coding.

## What seepage is (plain description, since the base paper isn't in your context)
When traffic is stopped at a red light, small vehicles (mainly two-wheelers, sometimes
three-wheelers) don't just wait in a straight queue behind the vehicle directly ahead of
them — they filter laterally into gaps between larger stopped vehicles (**lane filtering**)
and/or split forward between two adjacent vehicles to reach a position closer to the stop
line (**lane splitting**), as long as there is physically enough lateral and longitudinal
gap for their dimensions plus a safety margin. This changes departure order relative to
arrival order, which is exactly the "how does the order of vehicles change due to seepage"
question your teammate meeting notes raised.

## Steps

### 1. Extend `src/core/gaps.py`
Add the two seepage-specific gap functions per plan.md Eq 4-5 / Fig 6's 3-vehicle geometry:
- `seepage_lateral_gap(vehicle, left_neighbor, right_neighbor) -> tuple[float, float]`:
  returns `(gap_left, gap_right)` — the lateral clearance on each side of `vehicle` relative
  to the nearest stopped vehicles beside it, accounting for both vehicles' widths plus a
  configurable `lateral_safety_margin_cells` (add to config, default 0.5 cells).
- `seepage_longitudinal_gap(vehicle, front_left_vehicle, front_right_vehicle) -> float`:
  the forward gap available if `vehicle` moves diagonally into the space between two vehicles
  ahead, per Fig 6's geometry — minimum of the two diagonal clearances, minus a
  `longitudinal_safety_margin_cells` config value (default 1 cell).
Write `tests/test_gaps.py` additions: at least 3 fixtures — (a) ample gap on both sides
returns correct positive values, (b) blocked on both sides returns ~0/negative appropriately
signaling "no seep," (c) asymmetric gap (room on right, not left) returns correctly.

### 2. `src/intersection/seepage.py` (new)
Implement Algorithm 3's decision order EXACTLY as specified in plan.md §4: for each vehicle
eligible for seepage (see eligibility gate below), check in this priority order and take the
FIRST viable option:
1. **Left gap check**: if `seepage_lateral_gap` on the left, plus the vehicle's own width and
   safety margin, is sufficient → seep left (update `lateral_position_cells` and advance
   `position_cells` by the mode's per-step seepage advance rate, a new config value
   `seepage_advance_cells_per_step`, mode-specific, default smaller than normal max_speed).
2. **Right gap check**: same logic, seep right, if left wasn't viable.
3. **Front-diagonal gap check**: using `seepage_longitudinal_gap`, if there's room to move
   diagonally forward between two vehicles ahead → do so.
4. **Else**: reduce speed to 0 and stop (standard IZOI+red behavior from Phase 3 — call that
   existing function, don't duplicate).
- `is_seepage_eligible(vehicle, signal_state, izoi_flag) -> bool`: **gate this exactly as
  plan.md specifies** — only True if the vehicle is inside IZOI AND signal is RED (reuse
  Phase 3's `is_in_izoi` and the signal's `state_at`). Also gate by vehicle mode/size — add a
  config list `seepage_eligible_modes: [two_wheeler, three_wheeler]` (cars/buses do not seep;
  document this as consistent with the base paper's small-vehicle-filtering description).
- `attempt_seepage(vehicle, neighbors, config, rng) -> str` returns which action was taken:
  `"seep_left" | "seep_right" | "seep_diagonal" | "stopped"` — return this label because you
  will need it for the FIFO-order-violation analysis later (plan.md §10 candidate direction
  #1) and it's useful for the trajectory visualization's color-coding in Phase 10.
Write `tests/test_seepage.py` covering all 4 branches with hand-constructed fixtures, plus one
test asserting a `car` or `bus` vehicle is NEVER seepage-eligible regardless of gaps
(`is_seepage_eligible` returns False unconditionally for those modes).

### 3. Wire into `src/sim/sim_loop.py`
In the per-step pipeline, for vehicles where `is_seepage_eligible` is True, call
`attempt_seepage` INSTEAD OF the plain Phase-3 IZOI-red deceleration branch (seepage is a
more specific case of "in IZOI and red" — the eligibility check already implies that
condition). Log the returned action label as a new `seepage_action` column in the simulation
output DataFrame (null/`"n/a"` for non-eligible vehicles/timesteps).

## Validation
`notebooks/figures/phase5_seepage_trajectories.png`: produce a TWO-PANEL x-t (space-time)
trajectory plot for the same demand/signal scenario — left panel with
`seepage_eligible_modes: []` (seepage off, via a config override, not by ripping out code),
right panel with seepage on as configured. **Required visual result**, matching plan.md's
description of the base paper's Fig 18: the seepage-OFF panel shows clean, roughly parallel
queue trajectory lines (FIFO order preserved); the seepage-OFF panel shows irregular
trajectories where some two-wheeler lines visibly cross ahead of larger-vehicle lines that
arrived earlier (i.e., visual evidence of order change). Color trajectories by mode so this
crossing pattern is visible at a glance.

Also compute a simple FIFO-violation count: for the seepage-ON run, for every pair of
vehicles that arrived at the back of the same queue, check whether departure order at the
stop line matches arrival order; print the violation count and violation rate to
`PHASE_REPORT.md`. This is a lightweight preview of plan.md §10 candidate direction #1 — not
the full research contribution, just a working instrumentation hook for later.

## Acceptance criteria
- [ ] `pytest -q` passes, all prior phases' regression tests included.
- [ ] `phase5_seepage_trajectories.png` shows the qualitative on/off difference described
      above.
- [ ] `test_seepage.py`'s car/bus-never-eligible test passes.
- [ ] No seepage move ever results in two vehicles occupying the same cell (extend
      `test_intersection_no_collision.py` from Phase 4, or add a dedicated
      `test_seepage_no_collision.py`, to run specifically on a seepage-heavy scenario).
- [ ] `PHASE_REPORT.md` updated with `## Phase 5` section including the trajectory plot
      reference and the FIFO-violation count/rate.
- [ ] Git commit made.

## Explicitly out of scope
Full statistical FIFO-order research analysis is a Phase 10 / post-replication topic (plan.md
§10), not this phase — here you only need the instrumentation hook and a basic count.
