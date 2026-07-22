# PHASE 2 — Real-Time Graphical Rendering

## Before you start
Read `plan.md` in full. Requires Phase 1's `rule184.py` (the `step` function) passing its correctness check. This phase adds **only** visualization on top of Phase 1's already-correct engine — do not modify the core Rule 184 logic here.

## Goal of this phase
Open a real Pygame window that renders the Phase 1 engine running live: cells drawn as a row of squares, cars highlighted, the simulation stepping forward continuously, with basic zoom and pan controls. Still a single one-way lane, still no junctions.

## Steps

### 1. `src/render/pygame_view.py`
- Initialize a Pygame window (resizable, reasonable default size e.g. 1200x400).
- Represent the road as a horizontal row of cells; draw each cell as a small square — empty cells one color, occupied cells (cars) another color.
- Main loop: each frame (or every N frames, to control simulation speed independently of rendering framerate — add a configurable `steps_per_second` so the simulation doesn't run at an uncontrollable, monitor-refresh-rate-dependent pace), call Phase 1's `step()` function and redraw.
- Add a simple on-screen readout (text) of current step count, density, and measured flow (reuse Phase 1's `density_of`/`flow_at_step`).

### 2. Zoom and pan
- **Zoom:** mouse scroll wheel (or +/- keys) changes the pixel size of each rendered cell, so more or fewer cells are visible at once, centered on the current view.
- **Pan:** click-and-drag (or arrow keys) shifts which portion of the road array is visible in the window, for when the road is longer than fits on screen at the current zoom level.
- Write a small manual-test checklist (not an automated test — this is inherently interactive) in `PHASE_REPORT.md`: confirm zooming in/out changes visible cell count correctly, and panning at a zoomed-in level correctly reveals different parts of the road without any rendering glitches (cells appearing duplicated, gaps, or misaligned).

### 3. Basic playback controls
- Pause/resume (spacebar or a button).
- Step-once (advance exactly one Rule 184 step while paused — useful for debugging and for anyone watching to inspect behavior cell-by-cell).
- Reset (reinitialize the road at a chosen density and restart).
- A simple UI control (even a basic slider or +/- buttons, doesn't need to be polished yet — that's Phase 6/7) to set the initial density before reset.

### 4. `scripts/run_simulator.py`
- Entry point: launches the Pygame window with a default single-lane, periodic-boundary road at a configurable density.

## Validation
- Manually run the simulator and confirm: cars visibly move rightward each step (or wrap around at the periodic boundary), the on-screen flow/density readout updates and looks consistent with what's visibly happening (e.g. flow near 0 when the road is nearly empty or nearly full, flow near its peak at moderate density), pause/step/reset all work without crashing, and zoom/pan don't desync the visual road from the underlying array (i.e., what you see rendered always corresponds to the correct portion of the actual array — add a debug mode that prints the array index range currently visible, and manually spot-check it against what's on screen).
- Since this phase is inherently about interactivity, there is no automated correctness test beyond confirming Phase 1's underlying engine tests still pass unmodified (`pytest -q` should show zero regressions in `test_rule184.py`) — the manual-test checklist above is this phase's actual acceptance criterion, and should be documented as such in `PHASE_REPORT.md` with a plain description of what you observed.

## Acceptance criteria
- [ ] `pytest -q` — Phase 1 tests unmodified and still passing (confirms Phase 2 didn't touch the core engine).
- [ ] Pygame window opens, renders a moving Rule 184 simulation, with working pause/step/reset.
- [ ] Zoom and pan both work and don't desync from the underlying array (manually verified and documented).
- [ ] `PHASE_REPORT.md` updated with a `## Phase 2` section, including the manual-test checklist results.
- [ ] Git commit made.

## Explicitly out of scope
No junctions, no multiple lanes, no disruptions, no analytics beyond the basic on-screen flow/density readout, no map editing yet.
