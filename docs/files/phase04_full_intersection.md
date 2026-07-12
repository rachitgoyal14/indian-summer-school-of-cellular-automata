# PHASE 4 — Full 4-Leg Intersection Assembly + Turning Movements

## Before you start
Follow `00_START_HERE.md`. Requires Phase 3's `signal.py`, `izoi.py`, and single-leg
sim loop passing all tests.

## Goal of this phase
Wire 4 independent approach legs into one intersection (plan.md Fig 8a topology), each with
its own signal phase, vehicle generation, and turning-movement proportions, plus a conflict
resolution rule at the junction box. Reference plan.md §3 Phase 4 and §11 risk #1 (conflict
resolution is intentionally underspecified in the base paper — you must make and document an
explicit assumption).

## Steps

### 1. `src/intersection/routing.py`
- Function `choose_turn(mode: str, turn_proportions: dict[str, float], rng) -> Literal["left","straight","right"]`
  — weighted random choice from field-observed (or placeholder) proportions. Add to config:
  ```yaml
  turn_proportions:
    default: {left: 0.15, straight: 0.70, right: 0.15}
  ```
  (allow per-leg override later; `default` applied to all 4 legs for now — document this
  simplification.)
- Validate proportions sum to 1.0 per leg (raise `ValueError` if not, do not silently
  normalize — same pattern as Phase 2's mode_mix check).

### 2. `src/intersection/intersection.py` (the core new module)
- `Leg` class: wraps one approach — its own `Signal` instance (with a `phase_offset_s` so
  opposing legs can be green together and cross legs red, standard 2-phase operation: legs 0&2
  (N-S) share one phase, legs 1&3 (E-W) share the other), its own vehicle generator, its own
  IZOI/midblock pipeline from Phase 3, and a `stop_line_position_cells` / junction-box entry
  point.
- `Intersection` class: holds 4 `Leg` instances arranged N/E/S/W, a shared junction "box"
  region (a small 2D area where all 4 legs' movement paths overlap), and the top-level
  per-step update loop.
- **Conflict resolution rule (document this explicitly in code comments AND `PHASE_REPORT.md`
  as a modeling assumption, per plan.md §11 risk #1):** implement the standard
  right-hand-traffic convention used in Indian traffic — through/left-turning traffic has
  priority over opposing right-turning traffic; within the same approach, do not allow two
  vehicles to occupy the same junction-box cell in the same step (a vehicle whose intended
  path cell is occupied must wait one step and re-check, exactly like `decelerate_for_gap`'s
  existing gap logic — reuse that function against junction-box occupancy rather than writing
  new collision logic from scratch).
- `delete_vehicle_on_exit(vehicle, leg_geometry) -> bool`: once a vehicle's path takes it past
  the far edge of its destination leg, remove it from the simulation (plan.md's "vehicle
  deletion at end of approach/exit leg," Fig 8a red dots).

### 3. Update `src/sim/sim_loop.py`
Add `run_full_intersection(config, duration_s, mode_mix, rng) -> pd.DataFrame` that steps all
4 legs simultaneously each tick, applies routing at each leg's IZOI entry point (decide the
turn once, before the vehicle enters the junction box, not per-step), applies the junction-box
conflict rule, and logs `time_s, vehicle_id, mode, leg_origin, leg_destination, turn,
position_cells, lateral_position_cells, speed_cells_per_step`.

## Tests
- `tests/test_routing.py`: turn proportions sum-validation, and statistical check that over
  1000+ draws with a fixed seed, observed turn frequencies are within a reasonable tolerance
  (e.g. ±5 percentage points) of the configured proportions.
- `tests/test_intersection_no_collision.py`: run a short full-intersection simulation and
  assert no two vehicles ever occupy the same junction-box cell in the same timestep — this is
  the single most important correctness test in this phase, do not skip or weaken it.
- `tests/test_signal_phasing.py`: assert legs 0&2 are always in the same signal state as each
  other and always opposite to legs 1&3, at every timestep across 2+ cycles.

## Validation
`notebooks/figures/phase4_full_intersection_trajectories.png`: an x-y plan-view scatter/line
plot (or 4 small multiples, one per leg) showing vehicle paths from all 4 legs converging on
and passing through the junction box over a few signal cycles, colored by leg-origin. Visually
confirm: no crossing/overlapping trajectories at the exact same timestamp in the junction box,
and queues form and discharge independently on each leg per its own signal phase.

## Acceptance criteria
- [ ] `pytest -q` passes, all phases' regression tests included.
- [ ] `phase4_full_intersection_trajectories.png` produced and visually sane (4 legs, queues,
      turns visible).
- [ ] `test_intersection_no_collision.py` passes with zero violations over at least 2 full
      signal cycles of simulated time.
- [ ] `PHASE_REPORT.md` updated with `## Phase 4` section explicitly stating the conflict
      resolution assumption made (right-turn-yields-to-opposing-through), per plan.md §11 risk
      #1, and the 2-phase signal structure assumption.
- [ ] Git commit made.

## Explicitly out of scope
No seepage yet (Phase 5). Metrics/logging beyond what's needed for the tests above comes in
Phase 6 — don't over-build the collector here.
