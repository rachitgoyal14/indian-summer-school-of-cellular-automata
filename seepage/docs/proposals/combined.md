# Plan B: Combined Simulator — Seepage-Intersection Model + General Network Simulator

**Idea:** Don't discard the existing, validated, calibrated NaSch/seepage intersection work (Singh & Ramachandra Rao replication, Phases 0-7 already complete). Instead, treat it as the **traffic-dynamics engine** at the heart of a more general, visual, multi-scenario simulator — and selectively adopt the parts of the Genaro/Sukanta brief that make the existing work more presentable and useful, without regressing to a simpler model or diluting the core research contribution (seepage-driven vehicle reordering).

This plan is explicit about what's **kept**, what's **adopted** from the brief, and what's **deliberately dropped** — so nothing gets pulled in by default just because it was mentioned in the brief.

---

## 1. What stays exactly as-is (the engine)

Everything already built and validated is the foundation, not a component to be replaced:

- The full NaSch-based, non-lane-based, 4-vehicle-mode movement engine.
- The signalized 4-leg intersection, IZOI, and turning logic.
- **Seepage (Algorithm 3)** and the vehicle-ID-based order-tracking/overtake-event instrumentation — this is the actual research contribution and must not be weakened or replaced by a simpler rule.
- Calibration against real Kanagaraj field data, and the validation suite (Phases 7-8).
- Signal timing, IZOI distances, and other paper-sourced parameters.

**Explicitly rejected:** replacing the core motion rule with Rule 184. Rule 184 is a strict simplification (no speed variable, no randomization, single-lane only) relative to what's already built and validated. Adopting it would be a step backward in modeling fidelity, not an enhancement.

**Explicitly rejected:** dropping traffic signals. The brief says "no semaphores... time could be not good to consider such an option" — but signals, IZOI, and seepage-at-red-light are the entire basis of the existing work and the research question. This part of the brief does not apply to the combined direction.

---

## 2. What's adopted from the brief

Three genuinely additive ideas, pulled in deliberately rather than wholesale:

### 2.1 A real graphical, interactive front-end
The existing work produces static Matplotlib plots per scenario. The brief's vision of a live, zoomable, pannable visual simulator is a legitimate and valuable upgrade — it makes the existing (already-correct) simulation actually watchable and demoable, rather than just plot-based. This is the single biggest concrete improvement to adopt.

### 2.2 Live analytics: density, Shannon entropy, heatmaps
The brief's suggested analytics (density, entropy, log plots, heatmap) are a genuine addition to what's already measured (flow, density, delay, FIFO-violation rate). Shannon entropy in particular is a nice complementary lens: it can help distinguish "moderately dense but smoothly flowing" traffic from "the same density but jammed and clustered" — which is directly relevant to characterizing *how* seepage changes traffic state, not just whether it does.

### 2.3 Scenario save/load and comparison
The brief's "save and upload configurations at any time" maps cleanly onto what Phase 7's calibration work already does informally (comparing default vs. calibrated parameter sets). Formalizing this as a proper scenario-management system — save a full config (vehicle mix, signal timing, seepage on/off, calibration set) and reload/compare it later — is useful infrastructure for the eventual novel-research phase (Section 10 of the original plan), where several scenario variants will need to be run and compared systematically.

### 2.4 One disruption type, chosen deliberately (optional, stretch goal)
Rather than the brief's full library of disruptions (accidents, floods, fallen trees, parking, locks — most of which aren't relevant to a single signalized intersection), adopt **one**: a partial lane/road blockage (e.g. simulating a parked vehicle or an incident narrowing the effective road width). This connects directly and meaningfully to the existing research question — **does seepage's capacity benefit change when lateral road width is reduced?** — rather than being disruption-for-its-own-sake. This is explicitly a stretch goal, not core scope.

---

## 3. What's deliberately left out (and why)

| Brief item | Decision | Reason |
|---|---|---|
| Rule 184 as the core dynamics rule | Dropped | Existing NaSch model is strictly more capable and already validated |
| No traffic signals | Dropped | Signals are the entire basis of the existing work |
| Full campus/city-scale multi-road network editor | Dropped (for now) | A major separate scope of work (network topology, routing between many junctions); the current research value is concentrated at a single intersection. Could be a *future* extension once the single-intersection research question is answered, not a prerequisite. |
| Floods, fallen trees, parking, locks/gears | Dropped | Not relevant to a single signalized intersection; would dilute focus without adding research value |
| Accidents (two-car) | Dropped (for now) | Interesting but orthogonal to the seepage question; revisit only if time permits after core goals are met |

---

## 4. What the combined simulator actually delivers

A single, coherent piece of software that:

1. Simulates the real, validated, calibrated signalized-intersection-with-seepage model (unchanged core).
2. Renders it **live and interactively** — watch traffic build up, seepage happen, queues clear, with zoom/pan — instead of only producing after-the-fact static plots.
3. Displays **live analytics** (density, entropy, flow, FIFO-violation rate) alongside the visual simulation, updating in real time.
4. Lets you **save/load and compare scenarios** — different vehicle mixes, different signal timings, seepage on/off, default vs. calibrated parameters — as named, reusable configurations.
5. Optionally supports a **lane-width-reduction disruption**, directly extending the seepage research question into a new dimension (already flagged in the original plan's "candidate direction" list as a parameter sweep worth running).

This satisfies the spirit of the brief (a real, working, interactive traffic simulator with live analytics and scenario management) while keeping the actual research contribution — and everything already validated — fully intact.

---

## 5. Suggested tech stack

- **Simulation core:** unchanged (existing Python/NumPy engine).
- **Live rendering:** Pygame, driven directly by the existing simulation loop's per-step vehicle state (position, mode, lateral offset) — a rendering layer on top of the existing engine, not a replacement for it.
- **Live analytics panel:** either a secondary Pygame overlay or a lightweight web dashboard (Streamlit/Dash) reading from the same simulation state, updated per step or per N steps.
- **Scenario management:** JSON-based config save/load, extending the existing `configs/*.yaml` pattern already used for default vs. calibrated parameters.

---

## 6. Suggested build phases (additive to the existing 10-phase plan)

These are **new phases layered on top of the already-complete Phases 0-7 and in-progress Phase 8**, not a restart:

1. **Phase B1 — Rendering layer.** Build a Pygame view that reads the existing simulator's per-step output and draws vehicles, the intersection, and the signal state live. No new simulation logic — purely visualization of what already exists.
2. **Phase B2 — Live analytics panel.** Add real-time density, Shannon entropy, and flow plots alongside the rendered view, computed from the existing metrics layer (Phase 6).
3. **Phase B3 — Zoom/pan and basic interactivity.** Camera controls over the rendered intersection.
4. **Phase B4 — Scenario save/load.** Formalize config save/load and a simple UI to pick between saved scenarios (default params, calibrated params, seepage on/off, custom mode mix) and compare their live analytics side by side.
5. **Phase B5 (stretch) — Lane-width-reduction disruption.** Add a configurable partial-width blockage and measure its effect on seepage-driven throughput and reordering, extending the Phase 5 FIFO-violation analysis into a new parameter dimension.

---

## 7. Why this direction is the stronger pitch to Dr. Das

- It doesn't throw away validated, calibrated work — it makes that work *visible and demoable*, which is very likely also what a "no idea what you're doing" comment from an advisor actually wants to see.
- It genuinely satisfies the brief's spirit (interactive, visual, analytics-rich simulator with scenario management) without regressing the traffic model itself.
- It keeps the path to the actual novel research contribution (seepage-driven reordering, and potentially now lane-width sensitivity) fully open, rather than spending the remaining project time rebuilding a simpler Rule 184 simulator from scratch.
- It's honest about scope: a full multi-road city network with floods and accidents is explicitly deferred rather than silently dropped, so if that's later confirmed as a hard requirement, it's a known, scoped addition rather than a surprise.