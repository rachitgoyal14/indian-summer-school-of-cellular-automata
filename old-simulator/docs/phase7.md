# PHASE 7 — Demo Scenarios, Polish, Final Report

## Before you start
Read `plan.md` in full. Requires Phase 6's map editor and save/load working.

## Goal of this phase
Package a small set of ready-to-run demo scenarios, do a pass of UX polish, and write the final documentation/report — this is the "make it presentable" phase, not a new-feature phase.

## Steps

### 1. Build 3 demo scenarios using the Phase 6 map editor + save/load, saved to `demos/`:
- **`campus_loop.json`** — a small connected multi-junction network (case 5 from Phase 3) representing a simple campus-style loop road, moderate density, no active disruptions — a clean "everything working normally" baseline demo.
- **`flooded_segment.json`** — the same or similar network, with a flood disruption active on one segment, positioned so its downstream effect on the rest of the network is clearly visible (queue backing up into at least one upstream junction).
- **`accident_cascade.json`** — a network with an accident disruption placed such that its effect visibly cascades — i.e., the resulting queue grows long enough to back up traffic approaching a *second* junction, not just the one nearest the accident. This specifically demonstrates the "connected network" value of Phase 3's case 5, so pick a network layout and disruption placement where this cascading effect is clearly observable, not marginal.

For each demo, write a short paragraph in `PHASE_REPORT.md` describing what it demonstrates and roughly what a viewer should expect to see within the first minute of running it.

### 2. UX polish pass
- Add a basic in-app help overlay or key-bindings reference (toggleable, e.g. press `H`) listing: pause/step/reset, zoom/pan controls, map editor mode switches, save/load shortcuts, and how to toggle each disruption type and its slider.
- Confirm all on-screen labels (density/entropy/flow readouts, disruption toggles, landscape classification result) are legible and clearly labeled — a first-time viewer with no prior context should be able to tell what each number/control means without needing the README open.
- Fix any rough edges noticed during demo-building in step 1 (e.g. controls that are hard to hit precisely, unclear visual distinction between disruption types, laggy rendering at higher densities or larger networks) — this is expected; document what was found and fixed.

### 3. `README.md`
Write a real README for this repo: project description, citation of the original brief/proposal, setup instructions (`pip install -r requirements.txt`, how to run `scripts/run_simulator.py`), a short usage guide (key controls, how to load a demo scenario), and a summary of what's implemented against the brief's original ask (use `plan.md` Section 1's acceptance criteria list as the structure for this comparison, checking off each item honestly).

### 4. Final `PHASE_REPORT.md` wrap-up
Add a final `## Phase 7 — Wrap-up` section: paste plan.md Section 6's full deliverables checklist with each item marked done, and a short, honest "what would need more time" note for anything that's functional but rough (e.g. map editor UX, rendering performance on large networks) rather than implying everything is fully polished if it isn't.

## Acceptance criteria
- [ ] `pytest -q` passes — full regression suite, all phases.
- [ ] All 3 demo scenarios exist in `demos/`, load correctly via Phase 6's save/load, and behave as described in their `PHASE_REPORT.md` write-ups (manually confirm each one, actually run it, don't just assert the file exists).
- [ ] In-app help overlay implemented and covers all major controls.
- [ ] `README.md` complete, with an honest checklist comparison against the original brief's acceptance criteria (plan.md Section 1).
- [ ] `PHASE_REPORT.md` has a final wrap-up section per above.
- [ ] Git log shows at least 7 commits (one per phase minimum), working tree clean.

## After this phase
This is a natural point to demo the finished simulator directly to Dr. Das / Prof. Martinez, walking through each of the 3 demo scenarios live, rather than relying on plots or a written report alone — the brief specifically asked for an interactive tool, so the strongest way to show it's been delivered is to actually drive it live in the meeting.
