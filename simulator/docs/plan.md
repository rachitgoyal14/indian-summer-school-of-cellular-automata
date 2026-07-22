# Plan: General CA Traffic Simulator (Rule 184, Multi-Road Network, Interactive)

**Source brief:** Project proposed by Prof. Genaro Juarez Martinez, forwarded via Dr. Sukanta Das (IIEST Shibpur), June 2026.

**Goal of this document:** A hand-off plan for a coding agent to build the simulator **exactly as proposed** — an interactive, graphical, general-purpose road-network traffic simulator built on elementary cellular automaton Rule 184, with configurable disruption events and live analytics. This is a clean-room build, independent of any prior NaSch/seepage work.

This document is scope and architecture only — no code. Phase-specific implementation prompts (`phase1.md` through `phase7.md`) follow this plan and are meant to be handed to a coding agent one at a time, in order.

---

## 1. What "done" looks like (acceptance criteria for the full build)

By the end, the simulator should:

1. Render a road network (starting with a simple grid, extensible to arbitrary user-defined layouts) with vehicles moving on it, live, in a graphical window with zoom and pan.
2. Implement Rule 184 as the core vehicle-dynamics rule, correctly reproducing its known behavior (a moving "traffic jam front" at high density, free flow at low density — Rule 184 is exactly solvable and has a known flow-density relationship, which is a strong, checkable correctness target).
3. Support all 5 lane/junction configurations from the brief: one-way; two-way no interaction; two-way with turns; two-way both directions with turns; connected multi-junction networks.
4. Support all 8 "liberty degree" disruption types (breakdown, accident, flood, repair, lock/gate, fallen tree, parking, turning), each independently toggleable with a configurable probability, adjustable while the simulation is running.
5. Classify overall network state into trivial / average / worst landscapes based on aggregate congestion.
6. Display live density, Shannon entropy, log-scale, and heatmap plots alongside the running simulation.
7. Let a user save the current network + vehicle + disruption configuration to a file and reload it later.
8. Let a user directly edit the map (add/remove road segments, place/remove vehicles) through the interface.

None of this needs to model a specific real place — a synthetic, user-buildable grid network is sufficient and is what the brief implies ("campus university, town, or region of a city given" — i.e., *a* given region, not necessarily *the* same real region every time).

---

## 2. Core design decisions (made now, so the agent isn't guessing later)

- **Language/stack:** Python, NumPy for the grid, **Pygame** for real-time rendering and interaction. Rationale: the brief's language ("zoom-in and zoom-out with a scrollbar," "direct edition of cars in the map") describes a real-time interactive 2D application, which Pygame is well-suited for with a manageable learning curve; a web dashboard (Streamlit/Dash) would fight against true real-time animation and free-form map editing.
- **Grid representation:** each road is a 1D array of cells (a Rule 184 lane). A network is a collection of these 1D arrays connected at junction cells. This keeps Rule 184 itself simple (still fundamentally 1D per lane) while allowing 2D layouts.
- **Rule 184, precisely:** a cell (car) at position *i* moves to position *i+1* if and only if cell *i+1* is empty, applied to all cells simultaneously each timestep (synchronous update, standard CA convention — not sequential, which would change the dynamics). No speed variable, no randomization — this is what distinguishes it from NaSch and must not be "improved" by sneaking in NaSch-style rules.
- **Junctions:** a junction is a special cell shared by 2+ roads. When a car reaches a junction cell, it commits to an outgoing road according to configured turn proportions, then Rule 184 continues to apply on whichever road it's now on.
- **Disruptions as cell-state overlays:** rather than special-casing each disruption type in the movement rule, model every disruption as a cell temporarily or permanently marked "blocked" (impassable) or "restricted" (parking — removed from through-capacity). This keeps Rule 184's core logic completely unchanged; disruptions only affect which cells count as "empty."
- **Landscape classification:** compute as a simple thresholded function of (average network density, fraction of blocked cells, average queue length at junctions) — exact thresholds tuned empirically in Phase 6, not fixed in advance.

---

## 3. Phased roadmap

### Phase 1 — Core Rule 184 engine, no graphics
Single one-way lane, pure Rule 184, console/array output only. This is the correctness foundation — Rule 184 has a known, exactly-solvable flow-density relationship, so this phase's validation is a hard mathematical target, not just "looks reasonable."

### Phase 2 — Real-time graphical rendering
Add a Pygame window that renders the same Phase 1 engine live: draw cells/roads, animate cars moving, add zoom and pan. Still one lane, still no junctions — purely a visualization layer on top of Phase 1's already-correct engine.

### Phase 3 — Multi-lane and junction configurations
Implement the brief's 5 lane/junction cases: one-way (already done) → two-way no interaction → two-way with turning → full two-way both-direction turning → connected multi-junction network (e.g. a small grid of intersections).

### Phase 4 — Liberty degrees (disruption events)
Implement all 8 disruption types as toggleable, probability-driven cell-state overlays, each with its own UI control (slider/toggle) that takes effect immediately during a running simulation.

### Phase 5 — Live analytics
Add real-time density, Shannon entropy, log-scale, and heatmap plots, computed from the live simulation state and displayed alongside (or overlaid on) the Pygame view.

### Phase 6 — Landscape classification, map editing, save/load
Add the trivial/average/worst classifier, direct map editing (click to add/remove road segments and vehicles), and configuration save/load to JSON.

### Phase 7 — Polish, scenario demos, final report
Package a small set of demo scenarios (e.g. "campus loop at rush hour," "flooded segment," "accident cascading through a grid"), write the final report/documentation, and do a pass of UX polish (labels, legends, a basic help overlay).

**Do not skip phases.** Phase 1's correctness check is a hard mathematical target and the cheapest place to catch a bug — every later phase's disruptions and analytics are only meaningful if the base engine is verified correct first.

---

## 4. Rule 184 — the correctness target for Phase 1

Rule 184 is one of the few traffic CA rules with an exact, known analytical solution. For a system with density ρ (fraction of occupied cells) under periodic boundary conditions:

- **Flow (average fraction of cars moving per step)** = min(ρ, 1-ρ)

This is a hard, checkable target: at low density, flow rises linearly with density (free flow, flow ≈ ρ); at exactly ρ = 0.5, flow peaks at 0.5; above ρ = 0.5, flow falls symmetrically (flow ≈ 1-ρ) as the system becomes jammed. The flow-density curve is an exact **triangle**, not just triangle-shaped — this is Phase 1's acceptance criterion, and it should match almost exactly, not just qualitatively, since Rule 184 is deterministic and exactly solvable.

---

## 5. Suggested repo structure

```
ca-rule184-sim/
  README.md
  plan.md                     <- this file
  PHASE_REPORT.md
  configs/
    default_grid.json
  src/
    core/
      cell.py                 <- cell/road array representation
      rule184.py               <- the core movement rule
      junction.py               <- junction/turning logic
      disruptions.py            <- liberty-degree overlays
    network/
      grid_builder.py           <- builds a network of connected roads
      landscape.py               <- trivial/average/worst classifier
    render/
      pygame_view.py             <- main rendering + camera (zoom/pan)
      map_editor.py               <- click-to-edit road/vehicle placement
    analytics/
      density.py
      entropy.py
      heatmap.py
    io/
      scenario_io.py              <- save/load JSON configs
  scripts/
    run_simulator.py              <- main entry point
  tests/
  demos/
    campus_loop.json
    flooded_segment.json
    accident_cascade.json
```

---

## 6. Deliverables checklist per phase

- [ ] Phase 1: single-lane Rule 184 engine, flow-density curve matches the exact min(ρ, 1-ρ) triangle
- [ ] Phase 2: live Pygame rendering of Phase 1's engine, with zoom/pan
- [ ] Phase 3: all 5 lane/junction configurations working, verified with turning-proportion tests
- [ ] Phase 4: all 8 disruption types implemented and independently toggleable live
- [ ] Phase 5: live density, entropy, log-plot, and heatmap displays
- [ ] Phase 6: landscape classifier, map editor, save/load
- [ ] Phase 7: demo scenarios, final polish, documentation

---

## 7. Risks / things to flag early

1. **Synchronous vs. sequential update matters a lot for Rule 184.** Getting this wrong (updating cells one at a time instead of all-at-once from a snapshot) will silently break the exact flow-density relationship — this is the single most important implementation detail in Phase 1.
2. **Junction turning logic is not part of "pure" Rule 184** — the brief's own cited reference (Nagel, Wolf, Wagner & Simon, 1998) is specifically about extending single-lane CA rules to handle multi-lane/turning cases; treat Phase 3 as "informed by that paper's spirit," not as breaking Rule 184's core correctness guarantee from Phase 1.
3. **Real-time rendering performance.** A large network with many roads rendered every frame in Pygame can get slow; profile early once Phase 3's multi-junction networks are in place, before Phase 4 adds more per-cell state to check.
4. **Map editing UX is a real scope item, not an afterthought.** "Direct edition of cars in the map" (Phase 6) is often underestimated — budget real time for it rather than treating it as a quick final-phase add-on.
