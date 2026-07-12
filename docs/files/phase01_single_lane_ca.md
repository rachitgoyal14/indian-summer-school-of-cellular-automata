# PHASE 1 — Single-Lane, Single-Mode Midblock CA (Core Engine Smoke Test)

## Before you start
Follow all Ground Rules in `00_START_HERE.md`. This phase assumes Phase 0's repo skeleton,
config system, and `data/processed/trajectories_*.csv` already exist and `pytest -q` passes
on the Phase 0 code. If either is missing, stop and redo Phase 0 first.

## Goal of this phase
Implement the classic Nagel–Schreckenberg (NaSch) CA rules for **one vehicle mode only**
(use `car`), on a **straight single-lane road**, **no intersection, no lane changing, no
signal**. This is the smoke test that proves your core engine is correct before any
heterogeneity or 2D behavior is added. Reference: plan.md §3 Phase 1, and Algorithm 1's
core accel/decel/randomize/update-position pipeline (ignore the lateral-movement part of
Algorithm 1 for now — that's Phase 2).

## Data model to build

### `src/core/vehicle.py`
- A `Vehicle` dataclass with fixed properties set at creation: `id: int`, `mode: str`,
  `length_cells: int`, `max_speed_cells_per_step: int`, `max_accel_cells_per_step2: int`.
  For this phase, `mode` is always `"car"`. Use placeholder values you can justify:
  length 5 cells, max speed 5 cells/step, max accel 1 cell/step² (standard NaSch-textbook
  values — do not fabricate paper-calibrated values yet, those come in Phase 7).
  Mutable per-step state: `position_cells: int`, `speed_cells_per_step: int`.
- Write `tests/test_vehicle.py` checking a Vehicle can be constructed and its fields read back.

### `src/core/grid.py`
- A `Road` class representing a 1D array of cells of length `road_length_cells`, built from
  `configs/intersection_default.yaml`'s `grid.cell_length_m` and a new config field
  `road_length_m` (add `road_length_m: 1000` to the YAML under a new `midblock_test:` key
  so Phase-1-only config doesn't pollute the intersection config's top level).
- Method `occupancy_array(vehicles: list[Vehicle]) -> np.ndarray` returning a boolean array
  marking which cells are occupied (accounting for vehicle length).

### `src/core/motion.py`
Implement the 4 canonical NaSch sub-steps as 4 separate, independently testable pure
functions operating on a list of vehicles sorted by position (circular or open boundary —
use **open boundary** per the paper, not circular, since intersections are open systems):

1. `accelerate(vehicles) -> None`: each vehicle's speed += 1, capped at its max_speed.
2. `decelerate_for_gap(vehicles) -> None`: for each vehicle, compute the gap (in cells) to
   the vehicle ahead (front bumper of leader minus rear bumper of follower minus 1); if
   speed > gap, set speed = gap.
3. `randomize(vehicles, p_slowdown: float, rng: np.random.Generator) -> None`: with
   probability `p_slowdown` (config value, default 0.3), speed -= 1 (floor at 0). Must accept
   an explicit `rng` argument — never call `np.random` global state directly, so tests are
   reproducible with a fixed seed.
4. `update_positions(vehicles, road_length_cells) -> list[Vehicle]`: position += speed;
   vehicles whose position exceeds `road_length_cells` are removed (this is the "deletion at
   end of approach" behavior from plan.md's Fig 1/Fig 8a reference, simplified to a straight
   road for this phase).

Each of the 4 functions gets its own unit test in `tests/test_motion.py` using a small
hand-constructed 2-3 vehicle fixture where you can hand-compute the expected output.

### `src/sim/generator.py` (midblock-only version for this phase)
- `generate_vehicle_arrivals(rate_veh_per_hour: float, duration_s: int, rng) -> list[float]`:
  returns arrival timestamps drawn from an exponential (Poisson process) headway distribution
  — this is a legitimate simplification for Phase 1 (field headway distributions come from
  real data starting Phase 6); document this simplification in `PHASE_REPORT.md`.
- A vehicle is only actually inserted at the road's entry cell if that cell is free at its
  scheduled arrival time; otherwise it waits (queues) at the entry — do not silently drop it.

### `src/sim/sim_loop.py`
- `run_midblock_simulation(config: dict, duration_s: int, rng) -> pd.DataFrame`: wires
  generator → accelerate → decelerate_for_gap → randomize → update_positions into a
  per-second loop, and returns a long-format DataFrame with columns
  `time_s, vehicle_id, position_cells, speed_cells_per_step` logging every vehicle every step.

## Validation (this IS the acceptance criterion, not optional)
Create `notebooks/02_phase1_single_lane_sanity_check.ipynb` and `src/metrics/density_flow.py`
with a function `flow_density_from_log(df, road_length_cells, cell_length_m, window_s) -> pd.DataFrame`
that, for sliding time windows, computes:
- density (veh/km) = (avg number of vehicles on road in window) / (road length in km)
- flow (veh/hr) = (vehicles that crossed a fixed measurement point in window) × (3600/window_s)

Run the simulation at ~8-10 different arrival rates (e.g. 200 to 3000 veh/hr), plot flow vs
density. **The plot must show a NaSch-textbook triangular/parabolic shape**: flow rises
roughly linearly from density 0, peaks, then falls back toward 0 as density approaches
jam density. Save this plot to `notebooks/figures/phase1_fundamental_diagram.png`.

Add `tests/test_density_flow.py` with a hand-computable fixture (e.g. 2 vehicles, known
positions over 3 time steps) asserting `flow_density_from_log` returns the exactly expected
numbers — do not only eyeball the notebook plot, the math must be unit-tested too.

## Acceptance criteria
- [ ] `pytest -q` passes, including new tests for vehicle, motion (all 4 sub-steps), and
      density_flow.
- [ ] The FD plot in `notebooks/figures/phase1_fundamental_diagram.png` visually shows a
      rise-then-fall (triangular/parabolic) shape, not a flat line or monotonic curve. If it
      doesn't, debug `decelerate_for_gap` and `randomize` before moving on — this is the
      single most important sanity check in the whole project.
- [ ] `PHASE_REPORT.md` updated with a `## Phase 1` section, including the FD plot embedded
      or referenced, and the simplifications you documented (Poisson arrivals, generic NaSch
      params).
- [ ] Git commit made.

## Explicitly out of scope
No other vehicle modes, no lateral/2D movement, no signal, no intersection. Straight 1D road
only.
