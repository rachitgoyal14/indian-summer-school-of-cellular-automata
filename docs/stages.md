# stages.md — Execution Plan for plan.md (React + PixiJS Frontend)

This is the phase-by-phase build order. **Do not skip stages** — Stage 1's correctness check is a hard mathematical target and the cheapest place to catch a bug; every later stage's disruptions, analytics, and UI are only meaningful if the base engine is verified correct first. Hand these to a coding agent one stage at a time; each stage's acceptance criteria must be met, verified, and reported back before starting the next.

**Note on architecture:** the simulation engine is Python/NumPy throughout (Stage 1 is pure backend, no frontend at all). Starting in Stage 2, a React + PixiJS frontend connects to the Python backend over a WebSocket. This is a deliberate trade-off for visual quality over simplicity, made explicitly in `plan.md` Section 5 — do not revisit it mid-build.

---

## Stage 1 — Core Rule 184 Engine (Backend Only, No Frontend)

**Read `plan.md` Sections 5 and 6 first.**

Build (`backend/src/core/`):
- `cell.py`: 1D NumPy array road representation. `random_initial_state(length, density, rng)` — places an exact integer count of vehicles for a target density.
- `rule184.py`: `step(state, periodic=True) -> new_state`. Must be **synchronous** — compute the entire new state from a read-only snapshot of the old state, never mutate in place mid-computation. Support both periodic (ring road) and open boundaries.
- `backend/src/analytics/density.py` (minimal): `flow_at_step`, `density_of`.

Validation:
- `tests/test_rule184.py`: hand-computable fixtures, including one that specifically distinguishes correct simultaneous update from incorrect sequential update.
- Run a flow-density sweep: 15-20 density values from rho=0.05 to 0.95, periodic boundary, 500+ cells, enough warm-up steps to reach steady state, then measure flow over a further window. Plot against the theoretical min(rho, 1-rho) line.
- Required result: measured points sit almost exactly on the theoretical triangle. Since Rule 184 is deterministic, also verify: standard deviation of flow across the measurement window should be exactly (or near-exactly) zero at steady state, and results should be identical regardless of random seed used for the initial condition.

Acceptance criteria:
- [ ] pytest -q passes.
- [ ] Flow-density plot matches the theoretical triangle closely, attached as an image.
- [ ] Zero (or near-zero) variance and seed-independence at steady state, confirmed and explained.
- [ ] PHASE_REPORT.md created with a Stage 1 section.
- [ ] Git commit made.

---

## Stage 2 — WebSocket Server + Minimal React/PixiJS Client

**Read `plan.md` Section 5 in full — this stage is where the tech-stack decision actually gets built, so re-read the reasoning before starting.**

This is the highest-risk stage architecturally, since it introduces the client-server split for the first time. Budget real time for it; do not treat it as a quick wrapper around Stage 1.

### 2a. Backend: WebSocket server
Build (`backend/src/server/`):
- `ws_server.py`: FastAPI app with a WebSocket endpoint. On connection, starts (or attaches to) a running Stage 1 simulation loop; every tick (at a configurable steps_per_second, decoupled from anything the frontend does), serializes the current state and pushes it to all connected clients.
- `state_serializer.py`: converts the NumPy road state into a compact, frontend-friendly JSON message (e.g. step, occupied_cells, flow, density — decide the exact schema now and document it, since every later stage's messages extend this same schema).
- Also handle incoming messages from the frontend (to start, for Stage 2: pause/resume, single-step, reset-with-density) and apply them to the running simulation.

### 2b. Frontend: minimal React + PixiJS client
Build (`frontend/src/`):
- `hooks/useSimulationSocket.ts`: opens the WebSocket connection, exposes the latest received state to React components, and provides functions to send control messages back to the server.
- `components/SimulationCanvas.tsx`: a PixiJS Application embedded in a React component, rendering the road as a row of sprites (or a single dynamically-drawn texture, whichever performs better at scale — decide and document), updating each time new state arrives over the socket.
- Zoom (scroll wheel) and pan (drag), implemented via PixiJS's container transform (scale, position) — this should feel smoother than a software renderer; confirm it does.
- `components/ControlPanel.tsx`: pause/resume, single-step, reset with adjustable density.
- A live on-screen readout of step count, density, and flow.

### 2c. Latency and desync verification (new requirement specific to this architecture)
Explicitly test:
- Message ordering: confirm the frontend always renders states in the correct step order, even under artificial network delay (browser devtools throttling, or an artificial backend delay for testing) — a dropped-and-reordered message should not cause the display to visibly jump backward in time.
- Zoom/pan never desyncs from the actual road array — add a debug readout (visible cell index range) and manually confirm it matches what's rendered.
- Perceived responsiveness: pause/resume and single-step should feel immediate (sub-100ms round trip) on a local connection — measure and report actual round-trip time, don't just assume it's fine.

Validation:
- Manual test: confirm visible motion, on-screen flow/density readout consistent with what's happening, pause/step/reset all work, zoom/pan never desync.
- Capture evidence as a screen-recorded video (not a single screenshot) of the browser tab, at least 10-15 seconds, including a zoom and pan action — self-verify the capture actually contains multiple distinct frames with a progressing step counter before submitting.
- Report the message-ordering and round-trip-time checks explicitly, with actual numbers/observations.

Acceptance criteria:
- [ ] pytest -q — Stage 1 backend tests unmodified and passing.
- [ ] WebSocket server correctly streams state and receives control messages, manually confirmed.
- [ ] React/PixiJS client renders live motion, zoom, pan, pause/step/reset, all manually confirmed and feeling smooth, not just functional.
- [ ] Message-ordering and round-trip latency explicitly tested and reported, not assumed.
- [ ] Video/GIF evidence attached and self-verified.
- [ ] PHASE_REPORT.md updated with a Stage 2 section, noting the state message schema and the latency findings.
- [ ] Git commit made.

---

## Stage 3 — Vehicle Footprints + All 5 Lane/Junction Configurations

**Read `plan.md` Section 5 (footprint extension) and Section 2 (in-scope table) first.**

### Backend
- Extend cell.py/rule184.py so a vehicle can occupy a configurable multi-cell footprint (motorbike: 1 cell; car: 2-3 cells, exact values documented and justified). The movement check must correctly account for a vehicle's full footprint — write a specific test proving a car's full footprint is correctly treated as occupied, not just its front cell.
- junction.py: Junction class, configurable turn proportions per incoming road (validated to sum to 1.0), weighted random routing decision.
- Implement all 5 brief-listed cases in order: one-way [done] -> two-way no interaction -> two-way with turns -> two-way both directions with turns -> connected multi-junction network.
- grid_builder.py: procedural grid network construction.
- Extend the message schema for multiple roads, junction positions, and per-vehicle footprint/type.

### Frontend
- Extend SimulationCanvas.tsx to render multiple connected roads and junctions in a real 2D layout — junctions as distinct PixiJS graphics, roads as connected sprite chains, vehicles rendered with size proportional to their footprint.
- Confirm zoom/pan still works correctly across the full network.

Validation:
- test_junction.py: proportion-sum validation, and a statistical test confirming observed turn frequencies match configured proportions within reasonable tolerance.
- test_no_junction_collision.py: extended multi-junction run, zero cell-overlap collisions, including footprint-aware vehicles.
- Manually run case 5 in the browser and confirm reasonable turning behavior, visible size distinction between motorbikes and cars, and deliberately congest one junction to check whether growth over time reaching a neighboring junction is directly observable — via a fixed wide camera view from the start, or an always-visible per-junction queue-length readout, so this is verifiable and not inferred from a camera move.

Acceptance criteria:
- [ ] pytest -q passes — all regression tests plus new footprint, junction, and collision tests.
- [ ] All 5 lane/junction configurations manually confirmed working in the browser.
- [ ] Zero collisions confirmed over an extended run, including footprint-aware vehicles.
- [ ] Motorbikes and cars visually distinct by size.
- [ ] Congestion-propagation demonstration uses a camera-independent method.
- [ ] PHASE_REPORT.md updated with a Stage 3 section.
- [ ] Git commit made.

---

## Stage 4 — Unified Disruption Mechanism (All 8 Liberty Degrees)

**Read `plan.md` Section 4 first — do not build 8 independent systems; build the 3 underlying mechanisms and map all 8 brief terms onto them as specified.**

### Backend
- disruptions.py: temporarily-blocked single cell, temporarily-blocked multi-cell region, permanently-reserved manual-toggle cells, plus a repair/countdown clearing mechanism.
- Map all 8 brief terms onto these per plan.md's Section 4 table.
- Modify the movement check to also check disruption state. Regression test confirming Stage 1's exact flow-density correctness is unperturbed at all-disruptions-off.
- Extend the message schema so disruption state and type/label are included in every push; add handlers for the frontend's toggle/slider controls.

### Frontend
- Extend ControlPanel.tsx with live sliders/toggles for all 8 disruption types, labeled per the brief's own terms.
- Extend SimulationCanvas.tsx to render each disruption type with a visually distinct color/icon/effect — a good place to use PixiJS's strengths (glow/particle effects) rather than flat coloring.

Validation:
- test_disruptions.py: probability=0 never triggers, probability=1 always triggers where applicable, durations clear on schedule, permanently-reserved cells never clear on their own.
- Regression test: Stage 1 flow-density curve unchanged at all-disruptions-off.
- Manually trigger each of the 8 disruption types one at a time in the browser and confirm visual distinctness and expected behavior.

Acceptance criteria:
- [ ] pytest -q passes — all regression tests plus new disruption tests.
- [ ] Stage 1 baseline confirmed unperturbed at zero disruption probability.
- [ ] All 8 brief-named disruption types manually confirmed working, visually distinct, and live-adjustable from the browser.
- [ ] PHASE_REPORT.md updated with a Stage 4 section, noting which brief terms share which underlying mechanism.
- [ ] Git commit made.

---

## Stage 5 — Live Analytics (Density, Entropy, Log Plots, Heatmap)

### Backend
- entropy.py: shannon_entropy(state, window_size). Test with hand-computable fixtures: evenly-spread traffic (high entropy) vs. clustered (low entropy), with the actual expected numeric range for each.
- heatmap.py: per-road-segment congestion values, included in the state message.
- Extend the message schema with entropy and per-segment density.

### Frontend
- AnalyticsPanel.tsx: a live-updating chart showing density and flow over time on a log scale, plus a live Shannon entropy readout. Pick a charting approach that can keep up with frequent updates and document the choice.
- Heatmap overlay in SimulationCanvas.tsx using PixiJS tint/color, toggleable, with a documented priority relative to disruption-type coloring.

Validation:
- test_entropy.py passing with hand-computed fixtures.
- Manually cross-check the heatmap against what's directly visible in the main view.
- Manually confirm entropy behaves as expected across at least 2-3 different disruption scenarios, documented.

Acceptance criteria:
- [ ] pytest -q passes — all regression tests plus new entropy tests.
- [ ] Live density, entropy, log-plot, and heatmap all working in the browser without visibly degrading smoothness.
- [ ] Heatmap cross-checked against visible congestion and confirmed consistent.
- [ ] PHASE_REPORT.md updated with a Stage 5 section, including the entropy observations and charting choice.
- [ ] Git commit made.

---

## Stage 6 — Map Editor, Save/Load, Landscape Classification

**Read `plan.md` Section 3's note on map editing being real scope — doubly true now as a browser UI.**

### Backend
- landscape.py: classify_landscape(density, blocked_fraction, avg_queue_length) -> trivial/average/worst. Thresholds derived empirically, documented with the data behind them.
- scenario_io.py: save_scenario/load_scenario to/from JSON.
- Message handlers for map edits (add/remove road, add/remove vehicle, adjust turn proportions) and save/load requests.

### Frontend
- MapEditor.tsx: click-to-add-road, click to place/remove a vehicle, adjust turn proportions, a clear active-mode indicator, and a delete mode. Sends edits over the WebSocket; backend is the source of truth (frontend should not maintain its own drifting copy of state).
- Save/load UI.

Validation:
- test_landscape.py: at least one clear case per category, using empirically-derived values.
- test_scenario_io.py: save -> load -> assert exact match.
- Manual test: build a network from scratch in the browser editor, place vehicles, add a disruption, save, reload the page, load it back — confirm visual identity and correct re-sync to backend state.

Acceptance criteria:
- [ ] pytest -q passes — all regression tests plus new landscape and scenario I/O tests.
- [ ] Landscape thresholds empirically derived and documented.
- [ ] Map editor supports add/remove roads, add/remove vehicles, adjust turn proportions — manually confirmed.
- [ ] Save/load round-trips correctly, including a full page reload.
- [ ] PHASE_REPORT.md updated with a Stage 6 section.
- [ ] Git commit made.

---

## Stage 7 — Demo Scenarios, Polish, Documentation, Final Handoff

Build:
- 3 demo scenarios in demos/: campus_loop.json (clean baseline), flooded_segment.json (visible downstream queue effect), accident_cascade.json (effect cascades to a second junction).
- HelpOverlay.tsx: in-app controls reference.
- A genuine visual/UX polish pass: smooth transitions, consistent color language across disruptions and heatmap, legible typography, and confirmed performance (no visible stutter) at a reasonably large network size — profile and document actual frame timings.
- README.md: description, brief citation, setup instructions for BOTH backend (pip install, run server) and frontend (npm install, dev server), usage guide, and an honest checklist against plan.md Sections 2 and 3, including the tech-stack trade-off stated plainly.
- Final PHASE_REPORT.md wrap-up: plan.md Section 9's checklist, each item marked done, plus an honest "what's functional but rough" note.

Acceptance criteria:
- [ ] pytest -q passes — full backend regression suite, all stages.
- [ ] All 3 demo scenarios load correctly and behave as described when actually run in the browser.
- [ ] In-app help overlay covers all major controls.
- [ ] README.md complete with setup instructions for both backend and frontend, and the honest scope checklist.
- [ ] PHASE_REPORT.md has a final wrap-up section, including measured frame-timing/performance data.
- [ ] Git log shows at least 7 commits, working tree clean, both backend/ and frontend/ present and buildable from a fresh clone.

### After this stage
This is the point to demo it live to Dr. Das and Prof. Martinez — run both the backend server and frontend dev server, and walk through all 3 scenarios interactively. Worth testing the demo setup once beforehand on the actual machine it'll be shown on, not for the first time in the meeting.