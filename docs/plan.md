# plan.md — Interactive CA Traffic Simulator (Rule 184, React + PixiJS Frontend)

**Source brief:** Project proposed by Prof. Genaro Juarez Martinez, forwarded via Dr. Sukanta Das (IIEST Shibpur).

**What this document is:** the single source of truth for what gets built, what deliberately doesn't, and why. Every inclusion and exclusion below was chosen against one test: **does this make the simulator more useful for someone to sit down, play with, and learn something about traffic from — or does it just check a box in the original email?** Where those two things conflict, usefulness wins, and the deviation from the literal brief is stated openly rather than silently.

---

## 1. What this simulator is actually for

The brief's own stated purpose is: *"develop a software that could help to take decisions to plan, reorganize, redesign, and collapse avenues."* That's a decision-support / exploration tool, built for a person — likely Prof. Martinez or Dr. Das — to sit in front of, change something, and immediately see what happens. That single sentence is the design target for everything below. It is **not** primarily a research-statistics tool (no calibration against real data, no formal validation suite is in scope here — this is a distinct, simpler project from the seepage/NaSch intersection work already done).

---

## 2. What's IN scope, and why

| Feature | Why it's in |
|---|---|
| Rule 184 as the core movement rule | Explicitly specified — "this rule will determine all car dynamics" |
| Motorbikes and cars, different footprints | Explicitly specified as the initial vehicle set |
| Real-time Pygame rendering, zoom + pan (scrollbar-equivalent) | This is the entire stated interaction model — "the simulator will handle a zoom-in and zoom-out with a scrollbar," "updated and working all time" |
| Direct map editing (add/remove roads, place/remove vehicles) | Explicitly specified — "direct edition of cars in the map or random" |
| The 5 lane/junction configurations | Explicitly specified, case by case, in the brief |
| A curated set of "liberty degree" disruptions, built deep not wide (see Section 4) | Explicitly requested, but treated with judgment rather than a literal checklist — see reasoning below |
| Save/load configuration | Explicitly specified — "save and upload configurations at any time" |
| Live density, Shannon entropy, log-scale, heatmap displays | Explicitly specified |
| Trivial / average / worst landscape classification | Explicitly specified |
| A small, connected multi-junction "campus/town" network | Explicitly specified (case 5), and this is the actual planning-tool payoff — a single road segment doesn't let anyone reason about "redesigning an avenue" |

---

## 3. What's OUT of scope, and why (stated openly)

| Item from the brief | Decision | Reasoning |
|---|---|---|
| Buses | **Deferred, not day-one** | The brief itself says buses come "if [motorbikes and cars] become controlled correctly" — this is the brief's own conditional, not a cut we're inventing. Get 2 vehicle types genuinely solid first. |
| Traffic signals | **Excluded entirely** | The brief explicitly says so: *"No semaphores are considered at the moment, the time could not be good to consider such an option."* Including them would be scope creep against an explicit instruction, not an enhancement. |
| Real GIS / real map import for "a campus, town, or region of a city" | **Excluded — procedural grid network instead** | The brief says "given," implying a definable input, not a mandate to ingest real-world map data. Real map ingestion (road-network parsing, geocoding, etc.) is a substantial separate project with little payoff for the actual goal (a planner reasoning about *a* layout, not necessarily *this specific real* layout). A user-buildable procedural grid, extensible via the map editor, delivers the same exploratory value at a fraction of the engineering cost. |
| Every one of the 8 disruption types built as fully independent, bespoke systems | **Consolidated into fewer underlying mechanisms** | Several of the listed disruptions are mechanistically identical: a breakdown, a fallen tree, and (for a duration) an accident are all "this cell becomes unavailable for N steps, then clears." Building all 8 as genuinely separate subsystems would mean either shipping 8 shallow reskins of the same mechanism, or spending disproportionate engineering time on cosmetic distinctness instead of on the parts that actually matter (rendering quality, map editing feel, analytics). See Section 4 for exactly what's kept distinct vs. consolidated, and why. |
| NaSch-style speed variable / randomized braking | **Excluded** | Rule 184 has no speed variable and no randomization by design — introducing either would mean quietly building a different, more complex rule while still calling it "Rule 184," which misrepresents what was asked for and what was built. |
| Formal calibration against real-world traffic data | **Excluded** | Not requested by the brief, and orthogonal to its actual purpose (an exploratory planning tool, not a validated research replication — that already exists as a separate project). |

---

## 4. The disruption ("liberty degree") design, specifically

Rather than implementing 8 disconnected features, all disruptions share ONE underlying mechanism — a cell (or set of cells) can be in one of three states: **normal**, **temporarily blocked** (clears automatically after a duration), or **permanently reserved** (only clears manually). Every brief-listed disruption maps onto this:

| Brief's term | Underlying mechanism | Trigger |
|---|---|---|
| Fall car (breakdown) | Temporarily blocked, single cell | Probability-driven, per step |
| Accident (two cars) | Temporarily blocked, two adjacent cells | Probability-driven, per step |
| Flood | Temporarily blocked, a whole contiguous segment | Probability-driven or manually placed |
| Fallen tree | Temporarily blocked, single cell | Probability-driven, per step (same mechanism as breakdown, different label/color, since the brief lists it separately) |
| Repair | The automatic clearing of any temporarily-blocked state | Countdown-driven, always active |
| Locks/gears | Permanently reserved, manually toggled | Direct user control, not probability-driven |
| Parking | Permanently reserved, edge cells | Direct user control |
| Turn (change of direction) | Not a disruption at all — this is ordinary junction routing behavior (Section 2, already covered by the 5 lane/junction cases) | N/A |

This is a deliberate design choice: it means all 8 "liberty degrees" are genuinely present and independently controllable in the UI (each gets its own real-time slider/toggle, each visibly does something distinct on screen via color-coding), while the underlying code stays simple enough to actually get right and polish — which matters more for "best ever" than having 8 superficially different code paths.

---

## 5. Core design decisions

- **Tech stack — chosen explicitly for maximum visual quality, not just convenience.** The simulation engine (Rule 184, junctions, disruptions, analytics — all the actual logic and correctness) is **Python + NumPy**, unchanged from a simpler build: nothing about the math benefits from a different language. The **rendering layer** is a **React frontend using PixiJS** (a WebGL-accelerated 2D rendering library purpose-built for large numbers of smoothly animated sprites, camera zoom/pan, and visual effects like glow/particles/color blending) rather than Pygame. Python and the browser frontend communicate over a **WebSocket** connection (FastAPI backend): the simulation engine steps forward and streams state to the browser every tick; the frontend renders whatever state it receives and sends user actions (map edits, disruption toggles, camera moves) back as messages.

  **Why this instead of Pygame:** Pygame is a CPU-driven, software-rendered 2D toolkit — it can display the simulation correctly, but it structurally cannot deliver smooth anti-aliased scaling, GPU-accelerated glow/blur effects, or graceful performance with hundreds of independently animated sprites and live overlays. Since the explicit goal here is "the absolute best graphics and best simulator possible," not just a functionally correct one, PixiJS (WebGL, GPU-accelerated, built specifically for this kind of large-scale 2D animation) is a genuinely better fit for the actual ask, and a React frontend gives a much stronger foundation for the UI chrome (control panels, sliders, live analytics dashboards, the map editor) than hand-rolled Pygame widgets ever will.

  **What this costs, stated plainly, not hidden:** this is now a client-server architecture (a Python backend process + a browser frontend, connected over WebSocket) instead of one single desktop app. That's more moving parts than Pygame — a real network/sync layer between simulation and display, a second, separate frontend codebase (React + PixiJS, not just Python), and a meaningfully larger engineering surface overall. This trade is being made deliberately, in exchange for a genuinely better-looking, more impressive, more extensible result — it should not be revisited or second-guessed mid-build once Stage 2 begins, since switching rendering stacks partway through is far more expensive than picking one carefully now.

- **Grid representation:** each road is a 1D array of cells (a Rule 184 lane); a network is a set of these connected at junction cells. This keeps Rule 184 itself simple while allowing arbitrary 2D layouts. This representation lives entirely on the Python backend and is serialized (as JSON, or a more compact binary/array format if performance requires it later) to the frontend every tick — the frontend never needs to know about NumPy arrays directly, only the rendered positions/states derived from them.
- **Rule 184, precisely, extended minimally for vehicle size:** a car/motorbike occupies 1 or more consecutive cells (motorbike: 1 cell; car: 2-3 cells — exact sizes tuned in Phase 1). Movement rule stays exactly Rule 184's logic: a vehicle's front cell moves forward by one cell if and only if that next cell is empty — checked against the WHOLE multi-cell footprint of any vehicle occupying it, not just a single 0/1 flag. This is the one deliberate, minimal extension beyond "pure" Rule 184, needed to support heterogeneous vehicle sizes as the brief requires, and it's called out explicitly here so it's never mistaken for an accidental drift toward NaSch.
- **Synchronous (simultaneous) update — non-negotiable.** All cells update from a single snapshot of the previous state, never sequentially. This is what makes Rule 184 exactly solvable and checkable (see Section 6), and getting it wrong silently breaks correctness in a way that's easy to miss visually but easy to prove mathematically.
- **Junctions:** a shared cell where 2+ roads meet; a vehicle reaching a junction commits to an outgoing road per configured turn proportions, then continues under Rule 184 on the new road.
- **Landscape classification:** a simple thresholded function of network-wide density, fraction of blocked cells, and average junction queue length — thresholds derived empirically from actual simulation runs (Phase 6), not picked arbitrarily up front.

---

## 6. The one hard mathematical correctness target

Rule 184 under periodic boundaries has an exact, known solution: steady-state flow = **min(ρ, 1-ρ)**, a perfect triangle, with zero randomness once at steady state (unlike NaSch). This is Phase 1's acceptance bar — not "looks roughly triangular," but matching almost exactly, since Rule 184 is deterministic. Every subsequent phase builds on top of this and should never be allowed to compromise it — regression-test it after every phase that touches core movement logic (notably Phase 4, when disruptions modify cell availability).

---

## 7. Suggested repo structure

```
ca-rule184-sim/
  README.md
  plan.md                       <- this file
  stages.md                     <- phase-by-phase execution plan
  PHASE_REPORT.md
  backend/                       <- Python simulation engine + WebSocket server
    configs/
      default_grid.json
    src/
      core/
        cell.py                   <- road array + vehicle footprint representation
        rule184.py                  <- the core movement rule (synchronous, footprint-aware)
        junction.py                  <- junction/turning logic
        disruptions.py                <- the unified blocked/reserved-cell mechanism
      network/
        grid_builder.py                <- procedural grid network construction
        landscape.py                    <- trivial/average/worst classifier
      analytics/
        density.py
        entropy.py
        heatmap.py
      io/
        scenario_io.py                   <- save/load JSON configs
      server/
        ws_server.py                      <- FastAPI + WebSocket, streams state, receives UI events
        state_serializer.py                <- converts NumPy simulation state into a frontend-friendly message format
    scripts/
      run_server.py                        <- main backend entry point
    tests/
  frontend/                      <- React + PixiJS rendering client
    src/
      components/
        SimulationCanvas.tsx        <- PixiJS scene: renders roads, vehicles, junctions, camera zoom/pan
        ControlPanel.tsx              <- playback controls, disruption sliders/toggles
        AnalyticsPanel.tsx              <- live density/entropy/log-plot/heatmap displays
        MapEditor.tsx                    <- click-to-edit road/vehicle placement, sends edit events over the socket
        HelpOverlay.tsx                   <- in-app controls reference
      hooks/
        useSimulationSocket.ts             <- WebSocket connection, incoming state + outgoing event handling
      App.tsx
    package.json
  demos/
    campus_loop.json
    flooded_segment.json
    accident_cascade.json
```

---

## 8. What "best ever" actually means for evaluation

Given the brief's stated purpose (a decision-support tool someone plays with), the bar for quality is:

1. **The core physics is provably correct** (Section 6) — not persuasive-looking, mathematically checked. This is entirely independent of the rendering stack and must never be compromised for visual polish.
2. **The interaction feels good, not just functional.** Zoom/pan and map editing are where a "planning tool" either earns trust or doesn't — treat their polish as core scope, not a final-phase afterthought. This is precisely why PixiJS/React was chosen over Pygame (Section 5) — smooth, GPU-accelerated camera movement and click interactions are much easier to get feeling genuinely good in this stack.
3. **Every disruption is genuinely, independently, live-adjustable and visibly distinct** — even though they share underlying mechanisms (Section 4), a user should never be confused about which disruption they just triggered. Visual distinctness (color, glow, icon) is specifically easier to make look good with PixiJS's effects than with Pygame's flat rendering — lean into this.
4. **The analytics actually explain something** — e.g. Shannon entropy should visibly and understandably drop when a disruption clusters traffic, not just be a number nobody can interpret.
5. **The client-server split (Section 5) does not introduce lag or desync that undermines the "real-time" feel.** Since state now travels over a WebSocket rather than living in a single process, latency and dropped/out-of-order messages are a real risk that wasn't present in a single-process design — this must be explicitly tested (Stage 2), not assumed away just because it works on a fast local connection during development.
6. **It's honest about what it is.** No signals, no buses at launch, no real map data — these are documented as deliberate decisions in the README, not discovered later as gaps. The tech-stack trade-off (Section 5) — more moving parts in exchange for meaningfully better visuals — should also be stated plainly, not glossed over.

---

## 9. Deliverables checklist (traced to `stages.md`)

- [ ] Stage 1: Rule 184 core engine (Python/NumPy), flow-density curve matches min(ρ, 1-ρ) exactly — no frontend yet
- [ ] Stage 2: WebSocket server streaming engine state + minimal React/PixiJS client rendering it live, zoom/pan, playback controls, latency/desync verified acceptable
- [ ] Stage 3: Vehicle footprints (motorbike vs. car sizes), all 5 lane/junction configurations, rendered in PixiJS
- [ ] Stage 4: Unified disruption mechanism, all 8 liberty degrees live-controllable from the React control panel
- [ ] Stage 5: Live analytics — density, entropy, log plots, heatmap — rendered in the React analytics panel
- [ ] Stage 6: Map editor (React + PixiJS click handling), save/load, landscape classification
- [ ] Stage 7: Demo scenarios, visual/UX polish pass, documentation, final handoff