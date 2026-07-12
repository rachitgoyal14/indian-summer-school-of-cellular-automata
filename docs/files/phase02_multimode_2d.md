# PHASE 2 — Multi-Mode, Non-Lane-Based, 2D Lateral Movement

## Before you start
Follow `00_START_HERE.md` ground rules. Requires Phase 1's `Vehicle`, `motion.py` (4
sub-steps), `sim_loop.py`, and `density_flow.py` to exist and pass tests. Still midblock —
**no signal, no intersection** in this phase.

## Goal of this phase
Extend the Phase 1 engine to all 4 vehicle modes with mode-specific physical parameters, and
add **lateral (2D) movement** so vehicles can occupy any lateral position within the road
width (non-lane-based), not just a single lane. Reference plan.md §3 Phase 2, Algorithm 1's
"Lateral movement" step, and Table 2 for the parameter list per mode.

## Steps

### 1. Extend `src/core/vehicle.py`
- Add a `mode_registry.py` (new file, same folder) with a dict/dataclass table for all 4
  modes: `two_wheeler`, `three_wheeler`, `car`, `bus`. For each mode define (as CELL counts,
  derived from the grid's `cell_length_m=0.5`, `cell_width_m=0.7` in the config):
  - `length_cells` (longitudinal extent)
  - `width_cells` (lateral extent)
  - `max_speed_cells_per_step`
  - `max_accel_cells_per_step2`
  Use this relative ordering (do not need paper-exact numbers yet — Phase 7 calibrates them):
  two_wheeler smallest length/width and highest max speed & accel; bus largest length/width
  and lowest max speed & accel; three_wheeler and car in between with three_wheeler slightly
  smaller/slower than car. Write these as an explicit YAML block appended to
  `configs/intersection_default.yaml` under a `mode_params:` key (one sub-block per mode) —
  do NOT hardcode these in Python, load from config.
- `Vehicle` gains a `lateral_position_cells: int` (or float, your call — document it) field
  in addition to the existing longitudinal `position_cells`.

### 2. `src/core/gaps.py` (new)
Implement gap calculations needed for both lateral movement and (later) seepage, per
plan.md's Fig 6 / Eq 4-5 geometry, but only the lateral-gap and lane-changing-relevant subset
for this phase (front/back longitudinal gap you already have from Phase 1's
`decelerate_for_gap` — refactor that logic into this module and have `motion.py` call it, do
not duplicate):
- `lateral_gap(vehicle, other_vehicles) -> float`: minimum lateral clearance to the nearest
  vehicle(s) overlapping the relevant longitudinal range, on left and right sides separately
  — return a tuple `(gap_left, gap_right)`.
- `front_gap(vehicle, other_vehicles) -> float`: longitudinal gap to nearest vehicle ahead
  whose lateral position overlaps this vehicle's lateral extent (i.e., only vehicles actually
  "in the way," not just anywhere on the road — this is the key non-lane-based difference
  from Phase 1's simple single-lane gap).
Write `tests/test_gaps.py` with small 2-3 vehicle hand-computable fixtures for both functions.

### 3. `src/core/lane_change.py` (new)
Implement lateral position-seeking / "lane-changing" as described in Algorithm 1's lateral
movement step and the position-preference parameter (cite Pandey et al., referenced as (40)
in the base paper, as your algorithmic basis — you don't need the original Pandey paper text,
just implement the standard position-preference logic: a vehicle has a slight per-mode bias
toward its preferred lateral position, default = road-width-adjusted so two-wheelers prefer
edges, cars/buses prefer center — parameterize this, do not hardcode.):
- `decide_lateral_move(vehicle, gaps, position_preference: float, lane_change_prob: float, rng) -> int`
  returns `-1`, `0`, or `+1` cells of lateral shift. Logic: only shift if (a) a random draw is
  below `lane_change_prob`, (b) the target lateral cell(s) are free per `lateral_gap`, and
  (c) the shift moves the vehicle closer to `position_preference`. Must NOT allow moving into
  an occupied cell — this is a hard safety constraint, test it explicitly with a fixture where
  the "preferred" direction is blocked and assert the function returns `0`.
Write `tests/test_lane_change.py` covering: (a) normal free-lateral-move case, (b) blocked
case returns 0, (c) `lane_change_prob=0` always returns 0 regardless of gaps.

### 4. Update `src/sim/sim_loop.py`
Add a `run_midblock_simulation_multimode(config, duration_s, mode_mix: dict[str, float], rng)`
function (new function, keep Phase 1's single-mode one intact for regression testing) that:
- Generates vehicles across all 4 modes according to `mode_mix` proportions (must sum to 1.0;
  raise a clear `ValueError` if not, don't silently normalize).
- Runs per-step: accelerate → front-gap-based decelerate (via `gaps.py`) → lateral move
  (`lane_change.py`) → randomize → update longitudinal position.
- Logs `time_s, vehicle_id, mode, position_cells, lateral_position_cells, speed_cells_per_step`.

## Validation
In `notebooks/figures/`, produce `phase2_fundamental_diagrams_by_mode.png`: run the
multi-mode simulation at 8-10 traffic volumes (varying total demand, fixed mode mix), compute
per-mode AND mixed-traffic flow-density curves using an extended `density_flow.py` function
`flow_density_by_mode(df, ...) -> dict[str, pd.DataFrame]`.

**Required visual result**: capacity (peak flow) and the density at which it occurs should be
ordered `two_wheeler > three_wheeler > car > bus`, matching the qualitative shape described in
plan.md's reference to the paper's Figure 16. If the ordering comes out wrong, first check
your Table-2-placeholder parameter ordering in the config (step 1) before touching the motion
logic — a wrong ordering is almost always a config/parameter bug, not an algorithm bug.

## Acceptance criteria
- [ ] `pytest -q` passes (all Phase 1 tests still pass — do not break existing tests; all new
      gap/lane-change tests pass).
- [ ] `phase2_fundamental_diagrams_by_mode.png` shows the four-mode capacity ordering above.
- [ ] No vehicle ever ends a simulation overlapping another vehicle's occupied cells
      (add an explicit `tests/test_no_overlap.py` that runs a short multimode simulation and
      asserts zero cell-occupancy collisions at every logged timestep).
- [ ] `PHASE_REPORT.md` updated with `## Phase 2` section, chosen mode parameter values and
      why, and confirmation of the capacity ordering result.
- [ ] Git commit made.

## Explicitly out of scope
No signal, no IZOI, no intersection, no seepage yet.
