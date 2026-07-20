# Plan A: CA Traffic Simulator — As Literally Proposed

**Source:** Project brief forwarded by Dr. Sukanta Das (IIEST Shibpur), originally from Prof. Genaro Juarez Martinez.

**Scope:** A general-purpose, graphical, interactive CA traffic simulator for a campus/town/city road network, built around elementary CA Rule 184, with disruption events and live map editing. This is a **standalone plan** — it does not assume or reuse the seepage/intersection work already in progress; see Plan B for that combination.

---

## 1. What the brief actually asks for

Reading the proposal literally, it has four distinct pillars:

1. **A general road-network simulator** — not one intersection, but an arbitrary campus/town/city layout that a user can define.
2. **Rule 184 as the core vehicle-dynamics rule** — the simplest possible traffic CA rule (single-lane, no passing, binary occupied/empty cells), rather than a full NaSch-style model.
3. **A library of "liberty degrees"** — random or user-triggered disruption events layered on top of the base rule: breakdowns, accidents, floods, repairs, locked/gated roads, fallen trees, parking, and turning.
4. **An interactive graphical front-end** — real-time simulation, zoom/pan, live editing of the map and vehicles, save/load configurations, and live analytics (density, Shannon entropy, log-plots, heatmaps).

Explicitly **out of scope per the brief**: traffic signals ("no semaphores are considered at the moment").

---

## 2. Interpreting the ambiguous parts (stated assumptions, not asked back)

The brief is a short paragraph, not a spec — several things need a concrete decision to start building. Assumptions made here, to be confirmed with Dr. Das before finalizing:

- **"Campus university, town, or region of a city given"** → interpreted as: the network is user-*definable* (a simple graph/grid editor), not tied to one specific real place. Start with a synthetic grid network (streets crossing at right angles), since a real campus road-network dataset would need its own data-collection effort.
- **Rule 184 "will determine all car dynamics"** → interpreted as: Rule 184 governs single-lane forward movement (a car moves if the cell ahead is empty). The five listed lane configurations (one-way, two-way no interaction, two-way with turns, etc.) are **modifications of how Rule 184 is applied at intersections/junctions**, following the cited Nagel, Wolf, Wagner & Simon (1998) two-lane CA rules paper — not a departure from Rule 184 itself.
- **"Real time" liberty degrees** → interpreted as: each disruption type is a per-cell or per-road probability parameter, adjustable via UI sliders while the simulation runs, immediately affecting subsequent steps.
- **Graphics stack** → Python with a 2D rendering library (see Section 5) rather than C++/OpenGL, given the team's existing Python fluency and to keep the graphics layer from dominating the whole project timeline.

---

## 3. Core simulation model

### 3.1 Rule 184 (baseline)
A single-lane, one-directional CA rule: a cell (car) moves forward by one cell per timestep if and only if the cell immediately ahead is empty; otherwise it stays. This is the simplest possible traffic rule and, unlike NaSch, has **no speed variable and no randomization** — cars move at a uniform rate whenever possible.

### 3.2 Lane/junction configurations (per the brief's 5 listed cases)
Implement as five selectable network topologies, each building on Rule 184:
1. **Original, one-way** — single lane, single direction (pure Rule 184).
2. **Two-way, no interaction** — two independent one-way lanes side by side, no lane-changing.
3. **Two-way with left/right turns** — adds junction logic: at a cell marked as an intersection, a car probabilistically commits to straight/left/right per configured turn ratios.
4. **Two-way, two-way left/right** — bidirectional lanes in both cross streets, full 4-way turning.
5. **Connected-X interactions** — multiple case-4 intersections linked into a small network (e.g. a 3x3 grid of junctions), so disruptions and congestion can propagate between intersections.

### 3.3 Liberty degrees (disruption events)
Each implemented as an independent, toggleable, probability-driven modifier to the base grid:

| Event | Mechanism |
|---|---|
| Car breakdown ("fall car") | A cell is marked permanently blocked until "repaired" |
| Accident (two cars) | Two adjacent occupied cells become jointly blocked for a configurable duration |
| Flood | A contiguous road segment becomes fully impassable for a duration |
| Repairs | A blocked segment (from breakdown/accident/flood) is cleared after its duration elapses |
| Locks/gears (assumed: gated/closed roads) | A road segment can be manually toggled open/closed |
| Fallen tree | Single-cell blockage, similar to breakdown but road-side triggered rather than vehicle-triggered |
| Parking | A subset of edge cells are permanently reserved/removed from through-traffic capacity |
| Turn (change of direction) | Per-vehicle probability of turning at a junction, per Section 3.2 case 3+ |

### 3.4 Landscape classification
After each run (or live), classify overall network state into **trivial / average / worst** based on a threshold rule over aggregate density and/or fraction of blocked/congested cells — thresholds to be tuned empirically once the simulator is running, not fixed in advance.

---

## 4. Analytics & visualization

- **Density plot** — vehicles per cell (or per road segment) over time.
- **Shannon entropy plot** — measures how "disordered" vs. "clustered" the traffic distribution is at each step; useful for distinguishing free-flow from jammed states without relying on density alone.
- **Log-scale plots** — of density/flow, for visualizing behavior across a wide dynamic range.
- **Heat map** — spatial overlay on the network showing congestion intensity per road segment, updated live.
- **Zoom/pan** — standard 2D camera controls over the rendered network.
- **Save/load configuration** — serialize the network layout, vehicle positions, and active disruption settings to a file (JSON) and restore them.

---

## 5. Suggested tech stack

- **Core simulation:** Python, NumPy for the grid/array operations.
- **Graphics/UI:** Pygame (simplest path to real-time 2D rendering, zoom/pan, and mouse-based map editing) or, if a more "dashboard" feel is preferred, a Plotly Dash / Streamlit front-end driving a NumPy backend (easier live plots, harder real-time animation).
- **Recommendation:** Pygame for the core interactive simulator (this is what the brief's "zoom-in/zoom-out with scrollbar" and "direct edition of cars in the map" language implies), with a secondary Matplotlib/Plotly window or exported report for the density/entropy/heatmap analytics, rather than trying to force live analytics panels into the same Pygame window as a first pass.

---

## 6. Suggested build phases

1. **Phase A0** — Single straight one-way road, pure Rule 184, no graphics (console/array output only). Confirms the core rule is implemented correctly.
2. **Phase A1** — Add Pygame rendering: draw the grid, animate cars moving per Rule 184, basic zoom/pan.
3. **Phase A2** — Add case 2-4 lane/junction configurations (two-way, turning).
4. **Phase A3** — Add a small connected network (case 5) — multiple linked intersections.
5. **Phase A4** — Add liberty degrees one at a time (breakdown → accident → flood → repair → lock → fallen tree → parking), each with its own toggle/slider in the UI.
6. **Phase A5** — Add live analytics: density, Shannon entropy, log plots, heatmap overlay.
7. **Phase A6** — Add save/load configuration, map editing (click to add/remove roads, place vehicles).
8. **Phase A7** — Landscape classification (trivial/average/worst) + final polish and demo scenarios.

---

## 7. Honest scoping note

This is, on its own, a substantial software-engineering project — the graphics/interaction layer (Phases A1, A6 especially) is a meaningfully different skill set from the traffic-modeling work done so far, and building a genuinely usable live map editor with zoom/pan and click-to-edit is not a small task. If this direction is chosen, it's worth explicitly confirming with Dr. Das and Prof. Martinez how much of the "full interactive editor" experience is actually required for the project's evaluation, versus a good static/scenario-based version being acceptable — that materially changes the timeline.