# CA Seepage Simulator — Implementation Status Report

**Base paper:** Singh, M.K. & Ramachandra Rao, K. (2023). *Simulation of Signalized Intersection with Non-Lane-Based Heterogeneous Traffic Conditions Using Cellular Automata.* Transportation Research Record. DOI: 10.1177/03611981231211317

**Goal:** Faithfully replicate the paper's cellular automata model of a signalized intersection with non-lane-based heterogeneous traffic and seepage behavior, validate it against real field data, then use the working simulator as a platform for a novel research contribution (see Section 6).

**Status as of this report:** Phases 0–7 of 10 complete and accepted. Phase 8 (Validation) in progress.

---

## 1. What's been built so far

The implementation follows a strict phased build order — each phase's simulator behavior had to be validated (via tests, plots, and targeted diagnostics) before the next phase was allowed to build on top of it. This was deliberately conservative: a bug introduced early (e.g. in the core vehicle-movement rules) would otherwise silently corrupt every phase built afterward.

| Phase | What it built | Status |
|---|---|---|
| 0 | Repo scaffolding, config system, real field-data pipeline | ✅ Complete |
| 1 | Core NaSch vehicle-movement engine (single lane, single mode) | ✅ Complete |
| 2 | Multi-mode, non-lane-based 2D movement (4 vehicle types) | ✅ Complete |
| 3 | Traffic signal + Influence Zone of Intersection (IZOI) behavior | ✅ Complete |
| 4 | Full 4-leg intersection, turning movements, conflict resolution | ✅ Complete |
| 5 | **Seepage** (Algorithm 3) — the paper's core novel behavior | ✅ Complete |
| 6 | Data collection & metrics layer (flow/density per paper's Eq 6–15) | ✅ Complete |
| 7 | Parameter calibration against real field data | ✅ Complete |
| 8 | Statistical validation (GEH, Theil's U, RMSE, RMSPE) | 🔄 In progress |
| 9 | Delay estimation + comparison against highway capacity manuals | ⬜ Not started |
| 10 | Final visualization & consolidated report | ⬜ Not started |

---

## 2. Key results and findings so far

### 2.1 Real field data, not synthetic
The simulator is calibrated and tested against the **Kanagaraj et al. (2015) Chennai trajectory dataset** — real video-extracted vehicle trajectories from heterogeneous, non-lane-based Indian traffic — rather than synthetic placeholder data. The official vehicle-type classification (motorcycle, car, bus, truck, LCV, auto-rickshaw) was cross-checked against the dataset's own documentation, giving a real observed mode mix for this segment:

| Mode | Share of real traffic |
|---|---|
| Two-wheeler | 54.6% |
| Car | 26.7% |
| Three-wheeler (auto-rickshaw) | 15.1% |
| Bus | 3.6% |

### 2.2 Core physics validated against textbook theory
The engine's fundamental behavior — how traffic flow relates to density — was independently verified two ways: (a) demand-driven simulation (vehicles entering from an open boundary) and (b) density-seeded simulation (vehicles placed directly at a target density, bypassing the entry process). Both approaches reproduce the classic triangular flow-density curve expected from cellular automata traffic theory, confirming the underlying movement rules are physically correct before any paper-specific behavior was layered on top.

### 2.3 Mode ordering matches the paper's expectation
Once isolated from mixed-traffic proportion effects, per-mode capacity is correctly ordered **two-wheeler > three-wheeler > car > bus** — matching the qualitative shape the base paper reports (its Figure 16) — and the magnitude is consistent with the paper's own reported saturation flow range (~4,200–5,283 veh/hr for mixed traffic) once vehicle footprint and non-lane-based packing are accounted for.

### 2.4 Real paper values used throughout, not generic placeholders
Wherever the base paper reports an actual measured value, it was extracted and used directly rather than a generic textbook default:
- Grid geometry (cell size, lane width) — paper's Eq 7–9
- Vehicle dimensions and per-mode calibration parameters — paper's Table 2
- IZOI (deceleration-onset) distances — paper's Table 1 (car 187.4m, bus 111.3m, three-wheeler 141.1m)
- Signal cycle length and effective green time — paper's Table 5 (130s cycle, 30s effective green)
- Aggregate turning-movement proportion — paper's Table 5 (35% of vehicles turn)

Where the paper genuinely doesn't report a value (notably: two-wheeler IZOI distance — the paper's GPS data collection only covered cars, buses, and three-wheelers), this is explicitly flagged as a literature-derived placeholder rather than silently treated as real data.

### 2.5 Seepage implemented and produces the expected qualitative effect
Algorithm 3 (seepage: small vehicles filtering through gaps between stopped larger vehicles during red) is implemented and validated with a two-panel trajectory comparison (seepage on vs. off), confirmed collision-free even under heavy, oversaturated demand.

A quantitative instrumentation layer was also built to directly measure **how much seepage changes vehicle departure order relative to arrival order** — the exact open research question raised in our original meeting notes. Key finding: in a 6-cycle test run, seepage was directly responsible for **36 order-reversal events**, about 6.7% of all order changes observed. The **dominant** source of order changes turned out to be something else entirely — natural speed differences between vehicle types during the free-flow approach (faster two-wheelers passing slower buses before ever reaching the queue), which accounts for ~90%+ of reordering in both the seepage-on and seepage-off conditions. This is a genuinely useful finding for scoping a novel research direction: it tells us seepage's contribution to reordering is real but modest, and separable from a larger background effect.

### 2.6 Honest negative result from calibration
Phase 7 calibrated the model's driver-behavior parameters (speed, randomization, lane-change probability) against real field flow/density data using a genetic algorithm + local refinement, following the paper's own two-stage optimization approach (adapted to open-source tools). After fixing two data-pipeline bugs uncovered during the process (a demand-rate mismatch and a flow-measurement-point issue), the honest finding is: **the calibrated parameters did not reliably outperform the paper's own literature-reported (Table 2) defaults** on this field site — a 5-seed robustness check showed the calibrated set was actually worse than defaults in 2 of 5 runs, and the average improvement was within the noise floor of the stochastic simulation itself.

This is reported plainly rather than dressed up, because it's actually informative: it suggests either (a) the paper's Table 2 parameters are already well-suited to this kind of traffic, or (b) the available field data (a **midblock** road segment, not an actual signalized intersection — the real intersection dataset from the paper's authors was not available to us) isn't rich enough to meaningfully improve on literature values for intersection-specific behavior. The genuine value delivered by this phase was catching and fixing two real data-pipeline bugs, not the calibration result itself.

---

## 3. Engineering rigor — why this took longer than a naive build would

Several of the phases above required substantially more debugging than initially expected, because early, plausible-looking implementations turned out to have subtle but consequential bugs. A few worth naming, because they're representative of the kind of care that went into this replication rather than being a red flag:

- **A vehicle-insertion rule that silently capped achievable traffic flow** well below the road's real capacity — not discovered by watching the output "look reasonable," only caught by deliberately re-testing the engine with vehicles placed directly at a known density, bypassing the suspect component entirely.
- **A queue-size anomaly that looked like it could be a bug** (much more variance across signal cycles than pure random arrivals should produce) turned out, after separating upstream vs. downstream measurement, to be a real and correctly-modeled traffic phenomenon (platoon compression from mixed-mode speed differences) — an interesting result in its own right.
- **A junction-box conflict rule that silently deleted vehicles** rather than resolving their conflict was caught before it could corrupt every downstream flow/density measurement — replaced with an explicit vehicle-conservation accounting (generated = exited + forced-through + still-queued, exactly, every time) that is now a standing regression check.
- **A double-movement bug in the seepage logic** that let vehicles briefly cross the stop line during red was caught and fixed with an exact-match test before being allowed to propagate into the calibration/validation phases.

The overall discipline: every plot, every "this looks correct" claim, and every surprising number was required to be backed by an actual quantitative check or a real attached image before being accepted — not just a plausible explanation. This slowed early phases down but means the phases now underneath calibration and validation (7–8) are standing on a foundation that's been genuinely stress-tested, not just assumed correct.

---

## 4. What's left

### Immediate (finishing the replication)
- **Phase 8 — Validation** *(in progress)*: compute GEH, Theil's U (with bias/variance/covariance decomposition), RMSE, RMSPE, and a two-sample t-test comparing simulated vs. real field flow/density and speed/headway distributions, on a held-out data split. Target thresholds from the literature: GEH < 5, Theil's U < 20%.
- **Phase 9 — Delay & manual benchmarking**: estimate average intersection delay directly from the simulation and cross-check it against at least two published highway capacity manual formulas (Indo-HCM 2017, and a Webster-based manual), using the same real Table 5 parameters already extracted from the paper.
- **Phase 10 — Final report & visualization**: consolidate all figures and results into one narrative notebook, with an explicit, honest limitations section (covering the two-wheeler IZOI placeholder, the midblock-vs-intersection field data gap, the simplified turning-vehicle model, and the calibration finding above).

### After replication (the actual novel contribution)
Per the original plan, four candidate directions were identified for the "what's genuinely new" contribution, to be finalized with Prof. Kasyap once the replication is fully validated:

1. **Order-of-vehicles under seepage** — directly building on the FIFO-violation instrumentation already working in Phase 5 (Section 2.5 above). This is the most "shovel-ready" of the four, since the measurement infrastructure already exists.
2. **Calibration methodology comparison** — the paper itself flags calibration as understudied in this space; Phase 7's finding (calibration didn't beat defaults with available field data) is a natural jumping-off point for a methods-focused comparison (e.g. against Bayesian optimization or surrogate-model calibration).
3. **Signal-timing optimization under seepage-aware delay** — using the validated simulator as an environment for an optimization/RL agent, since none of the standard capacity manuals model seepage's capacity benefit.
4. **Two-wheeler safety cost of seepage** — combining seepage trajectories with a conflict/near-miss detector to quantify the safety trade-off the paper itself raises but never measures.

---

## 5. Known limitations to flag transparently

- **Two-wheeler IZOI distance** is a literature-derived placeholder (100m), not a paper-reported value — the base paper's GPS deceleration data only covered cars, buses, and three-wheelers.
- **Available field data is midblock, not intersection-level.** The paper's own Delhi/Mumbai intersection data was not publicly available; the Kanagaraj dataset used for calibration is a real, published, heterogeneous-traffic dataset, but from an open road segment, not a signalized junction. This limits which parameters could be meaningfully calibrated (car-following/lane-changing behavior, yes; intersection-specific behavior like IZOI and turning proportions, no — those remain at literature values).
- **Junction conflict resolution is a simplified model.** The base paper doesn't fully specify how simultaneous conflicting turning movements resolve inside the intersection box; a standard right-turn-yields-to-through convention was implemented as an explicit, documented modeling choice.
- **Turned vehicles don't continue as live traffic on their destination leg** in the current model — they're removed once they clear the junction box rather than continuing to interact with that leg's own queue/signal. This is flagged as a scope limitation to revisit if Phase 9's delay comparison shows it matters.
- **Single-objective GA + local refinement was used in place of the paper's MATLAB multi-objective `gamultiobj` + goal-attainment hybrid.** Distributional/behavioral replication (correct ordering, correct queue dynamics) was prioritized over exact parameter-value replication, consistent with what's realistically achievable with open-source tooling.

---

*This document reflects the state of the implementation through Phase 7 (accepted) and the start of Phase 8 (in progress). It will be updated as Phases 8–10 complete.*