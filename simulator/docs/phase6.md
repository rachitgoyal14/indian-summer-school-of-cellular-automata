# PHASE 6 — Landscape Classification, Map Editing, Save/Load

## Before you start
Read `plan.md` in full, especially Section 7 risk #4 (map editing is a real scope item, budget real time for it). Requires Phase 5's live analytics working.

## Goal of this phase
Add the trivial/average/worst landscape classifier, a genuine click-to-edit map interface, and configuration save/load to JSON.

## Steps

### 1. `src/network/landscape.py`
- `classify_landscape(network_density: float, blocked_fraction: float, avg_junction_queue_length: float) -> Literal["trivial", "average", "worst"]`.
- Thresholds are NOT specified by the brief — determine them empirically: run the simulator across a deliberately wide range of density and disruption-severity combinations (reuse Phase 1's density sweep approach, now applied to a full network with disruptions active), observe where "obviously fine," "obviously congested but moving," and "obviously gridlocked" transitions happen in your own data, and set threshold values based on that. Document the actual threshold values chosen and the reasoning/data behind them explicitly in `PHASE_REPORT.md` — do not pick arbitrary round numbers without justification.
- Write `tests/test_landscape.py` covering at least one clear case per category (e.g. very low density/no disruptions → trivial; moderate density with an active accident → average; very high density with multiple active disruptions → worst) using values drawn from your own empirical sweep, not invented numbers.

### 2. `src/render/map_editor.py`
This is a genuine, real feature — treat it with the seriousness the brief implies ("direct edition of cars in the map or random"):
- Click on an empty area to add a new road segment (click-drag from one point to another to define a segment's start/end, or a simpler grid-snapped click-to-extend interaction — pick whichever is more reliable to implement well, document your choice).
- Click on an existing road cell to toggle a car on/off at that position.
- Click on a junction (or an appropriate UI control) to adjust turn proportions for that junction.
- A basic "delete" mode to remove a road segment or a car.
- Clear visual feedback for which edit mode is currently active (e.g. an on-screen label: "Mode: Add Road" / "Mode: Place Car" / "Mode: Delete").

### 3. `src/io/scenario_io.py`
- `save_scenario(network, disruption_config, path: str) -> None`: serialize the full network layout (roads, junctions, turn proportions), current car positions, and active disruption settings (probabilities, durations, locked/gated states) to a JSON file.
- `load_scenario(path: str) -> (network, disruption_config)`: reconstruct a full running scenario from a saved file.
- Write `tests/test_scenario_io.py`: save a scenario, load it back, and assert the reconstructed network/disruption state matches the original exactly (same road layout, same car positions, same disruption settings) — not just "loads without crashing."
- Add a UI control (simple button or keyboard shortcut) to save the current state and to load a previously saved file, with a basic file-picker or a fixed `demos/` directory listing to choose from.

## Validation
- `tests/test_landscape.py` and `tests/test_scenario_io.py` passing.
- Manually build a small network using the map editor from scratch (starting from an empty canvas, not a pre-built demo), place some cars, add a disruption, save it, restart the simulator, and load it back — confirm in `PHASE_REPORT.md` that the reloaded scenario is visually identical to what was saved (same roads, same cars, same disruption state).
- Confirm the landscape classifier's live readout changes appropriately as you manually trigger disruptions or adjust density through the editor while watching the simulation run.

## Acceptance criteria
- [ ] `pytest -q` passes — all regression tests plus new landscape and scenario I/O tests.
- [ ] Landscape classification thresholds empirically derived and documented, not arbitrary.
- [ ] Map editor supports add/remove roads, add/remove cars, and adjust turn proportions, all manually confirmed working.
- [ ] Save/load round-trips correctly, confirmed both by automated test and manual visual check.
- [ ] `PHASE_REPORT.md` updated with a `## Phase 6` section covering all of the above.
- [ ] Git commit made.

## Explicitly out of scope
Final demo scenario packaging and documentation polish is Phase 7.
