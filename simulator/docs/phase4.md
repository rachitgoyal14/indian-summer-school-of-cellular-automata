# PHASE 4 — Liberty Degrees (Disruption Events)

## Before you start
Read `plan.md` in full, especially Section 2's "disruptions as cell-state overlays" design decision. Requires Phase 3's multi-junction network working with zero collisions.

## Goal of this phase
Implement all 8 disruption types from the brief, each as an independently toggleable, probability-driven modifier — **without changing Rule 184's core movement logic**. Every disruption should be expressible as "this cell (or these cells) is temporarily or permanently not available as a destination," which Rule 184's existing "move only if target cell is empty" rule already handles correctly once you mark the right cells as unavailable.

## Steps

### 1. `src/core/disruptions.py`
Represent disruption state as a separate overlay array (or dict of blocked-cell-ids), not by modifying the road's car-occupancy array directly — this keeps a clean separation between "where cars are" and "what's blocked," which matters once you need to both render them differently and let blockages clear over time independent of car movement.

Implement each as a small, independently testable function/class:

- **Breakdown ("fall car"):** pick a cell with a car; that cell becomes permanently blocked (car "removed" from active simulation, cell marked unavailable) until repaired.
- **Accident (two cars):** pick two adjacent occupied cells; both become jointly blocked for a configurable duration (in steps), then automatically clear.
- **Flood:** a configurable contiguous stretch of cells on a chosen road becomes fully blocked for a configurable duration, then clears.
- **Repair:** the mechanism that clears a breakdown/accident/flood blockage after its duration elapses, or on manual trigger — implement as a countdown per blocked cell/region, decremented each step, cell becomes available again at zero.
- **Lock/gate:** a manually toggleable open/closed state on a chosen road segment (not probability-driven like the others — this is a direct on/off control, since "locks or gears" reads as an intentional closure rather than a random event).
- **Fallen tree:** functionally identical to breakdown (single-cell permanent blockage until repaired) but conceptually road-triggered rather than vehicle-triggered — implement with its own named function even though the mechanism is shared with breakdown, so the UI/analytics layer can label and count them separately.
- **Parking:** a configurable subset of edge-of-road cells are permanently reserved (blocked from through-traffic) rather than temporarily blocked — this doesn't clear on its own like the others, only via manual toggle.
- **Turning ("change of direction"):** already implemented in Phase 3's junction turn-proportion logic — this phase should just confirm it's independently configurable per the same "liberty degree" pattern (i.e., exposed as a live-adjustable parameter, not hardcoded).

Each disruption type needs a probability (or count/duration, as appropriate) parameter that lives in config, and a corresponding `tests/test_disruptions.py` test: e.g. for breakdown, assert that setting the probability to 0 never blocks a cell over many steps, and setting it to 1 always does; for accident, assert the affected cells clear again after exactly the configured duration; for parking, assert reserved cells never become available for through-traffic regardless of duration/repair.

### 2. Update `src/core/rule184.py` (minimal, careful change)
Modify the "is target cell empty" check to also check "is target cell blocked by an active disruption" — a car should not move into a blocked cell even if no car currently occupies it. This is the only place existing Rule 184 logic needs to change, and it should be a small, additive check, not a rewrite. Add a regression test confirming Phase 1's original flow-density correctness check (Section 4 of plan.md) still holds when all disruptions are set to zero probability (i.e., disruptions must be fully "off" by default and not silently perturb the validated baseline).

### 3. Update `src/render/pygame_view.py`
- Render each disruption type with a visually distinct marker/color on affected cells (breakdown, accident, flood, fallen tree, parking, and locked/gated segments should all look different from each other and from normal empty/occupied cells).
- Add live UI controls (sliders or +/- buttons is fine, doesn't need to be polished) for each disruption's probability/duration, adjustable while the simulation is running, with the effect visible within a few steps of adjustment.

## Validation
- `tests/test_disruptions.py` passing for all 8 types.
- Regression test confirming Phase 1's exact flow-density curve is unchanged when all disruption probabilities are 0.
- Manually run the simulator with each disruption type enabled one at a time (and then a couple together) and confirm in `PHASE_REPORT.md`: describe what you observe for each — does traffic visibly back up behind a flood/accident/breakdown, does it clear again after the repair duration, does parking permanently reduce visible capacity without ever clearing, does the lock/gate toggle correctly open and close on command.

## Acceptance criteria
- [ ] `pytest -q` passes — all regression tests plus the 8 new disruption tests.
- [ ] Phase 1's flow-density correctness confirmed unperturbed at zero disruption probability.
- [ ] All 8 disruption types manually confirmed working and visually distinct in the Pygame viewer, with live-adjustable controls.
- [ ] `PHASE_REPORT.md` updated with a `## Phase 4` section documenting each disruption type's manual test result.
- [ ] Git commit made.

## Explicitly out of scope
No analytics beyond basic flow/density yet (Phase 5), no map editing/save-load (Phase 6), no landscape classification (Phase 6).
