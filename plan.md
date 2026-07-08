# Plan: Cellular Automata Simulator for Signalized Intersections with Non-Lane-Based Heterogeneous Traffic & Seepage

**Base paper:** Singh, M.K. & Ramachandra Rao, K. (2023). *Simulation of Signalized Intersection with Non-Lane-Based Heterogeneous Traffic Conditions Using Cellular Automata.* Transportation Research Record. DOI: 10.1177/03611981231211317

**Goal of this phase:** Faithfully re-implement the paper's CA model (single isolated signalized cross-intersection, 4 vehicle modes, IZOI-based behavior switching, seepage) end-to-end as a working simulator, calibrate/validate it the way the paper does, and reproduce its headline results (FDs, delay comparison vs. manuals, seepage trajectory plots). Only **after** a working, validated replication do we branch into a novel problem statement (see Section 10).

This is a hand-off document for a coding agent. It intentionally contains **no code** — only scope, architecture, algorithms-to-implement, data sources, and acceptance criteria.

---

## 1. What "success" looks like (acceptance criteria for replication)

By the end of this implementation, the simulator should be able to reproduce, on your own field/proxy data:

1. A single isolated 4-leg signalized cross-intersection, non-lane-based, open boundaries, 4 vehicle modes (two-wheeler, three-wheeler, car, bus/truck).
2. An **Influence Zone of Intersection (IZOI)** that switches vehicle behavior rules as vehicles approach the stop line.
3. **Seepage** behavior — small vehicles filtering/splitting through gaps between stopped larger vehicles to reach the stop line during red.
4. Flow–density (fundamental) diagrams per mode and mixed traffic, roughly matching the qualitative shape in the paper's Figure 16 (capacity/density ordered two-wheeler > three-wheeler > car > bus).
5. A calibration loop that tunes the ~11 per-mode parameters (Table 2) against field flow/density using an optimization routine (paper uses genetic algorithm + goal attainment; a simpler single-objective GA or even coordinate descent is an acceptable first pass).
6. A validation suite reproducing the paper's statistics: GEH, Theil's U (+ bias/variance/covariance decomposition), RMSE, RMSPE, two-sample t-test on flow.
7. A delay module that estimates average intersection delay from the simulation and cross-checks it against at least 2–3 of the highway capacity manual formulas in Table 5 (Indo-HCM 2017, HCM 2010, and one more — pick whichever has the simplest closed-form, e.g. Webster-based Indonesian/Canadian manual).
8. Trajectory plots (distance–time) that visually reproduce the qualitative seepage vs. non-seepage pattern in Figure 18.

None of these need to match the paper's numbers exactly (you don't have their exact Delhi/Mumbai field data) — they need to be **internally consistent and directionally correct** on whatever data you calibrate against.

---

## 2. Paper → Module Mapping

Read this as the master checklist. Each row is a paper concept that needs a corresponding simulator component.

| Paper concept | Section/Fig/Eq/Alg in paper | Simulator module |
|---|---|---|
| CA grid & cell size (0.5m × 0.7m cells, 3.5m lane width per direction) | "Flow and Density Calculation" | `grid.py` — grid/geometry config |
| Vehicle modes & fixed dims (Table 2: length/width in cells) | Table 2 | `vehicle.py` — mode registry |
| Vehicle object model (fixed vs public properties, ID, position, speed, accel) | Algorithm 1 | `vehicle.py` |
| Vehicle generation per leg from field headway distribution | Fig 1 step 2 | `generator.py` |
| Gap calculation (front/back/left/right/lateral) | Fig 1 step 3, Fig 6, Eq 4–5 | `gaps.py` |
| Core NaSch-style movement rules (accel/decel/randomization/position update) | Algorithm 1, "Vehicle Modeling" | `motion.py` |
| Lane-changing / lateral movement (probability + position preference) | Algorithm 1 "Lateral movement", ref (40) | `lane_change.py` |
| IZOI: distance-based behavior switch (decelerate w/ field rate vs. continue as midblock) | Algorithm 2, Fig 2, Eq 3 | `izoi.py` |
| Signal state machine (red/green, cycle length, phase) | Fig 1 decision diamond "Is signal red?" | `signal.py` |
| Seepage / creeping behavior (small vehicle filters through gaps near stop line) | Algorithm 3, Fig 5, Fig 7, Eq 4–5 | `seepage.py` |
| Turning movement selection (L/R/straight per field-observed proportions) | Fig 1 "Decide the direction to choose" | `routing.py` |
| Vehicle deletion at end of approach/exit leg | Fig 1, Fig 8a (red dots) | `sim_loop.py` |
| Full intersection assembly (4 legs × modes × IZOI × seepage × signal) | Fig 8 | `intersection.py` |
| Data collection during run (flow, density, speed, headway, trajectories, queues) | Fig 1 last step | `collector.py` |
| Calibration (GA + goal attainment against flow/density) | Eq 16, Fig 9 | `calibration.py` |
| Macroscopic validation (t-test, FD comparison) | Table 3, Table 4, Fig 10 | `validation_macro.py` |
| Microscopic validation (headway/speed/trajectory comparison, Theil's U, RMSE, RMSPE, GEH) | Eq 17–23, Fig 11–15 | `validation_micro.py` |
| Delay estimation from simulation + manual formulas | Table 5, Fig 17 | `delay.py`, `manuals/*.py` |
| Seepage visualization (trajectory plots with/without seepage) | Fig 18 | `viz.py` |

---

## 3. Phased Roadmap (do NOT try to build all of this at once)

### Phase 0 — Environment & scaffolding
- Repo skeleton, config system (YAML/JSON for road geometry, cycle length, mode mix, calibration bounds), logging, unit test harness.
- Decide grid representation (dense NumPy array of cell occupancy vs. sparse vehicle-position list — recommendation in Section 7).
- Load/inspect whichever dataset you pick first (Section 5) and write a small script that just plots raw trajectories/headways, so you understand the data before you simulate anything.

### Phase 1 — Single-lane, single-mode, midblock CA (no intersection yet)
- Implement classic NaSch-style rules (acceleration, randomized slowdown, deceleration to avoid collision, position update) for **one vehicle type only**, straight road, **no** intersection, **no** lane changing.
- Validate: fundamental diagram (flow vs density) should look like a standard NaSch triangular/parabolic curve. This is your smoke test that the core engine is correct before adding complexity.

### Phase 2 — Multi-mode, non-lane-based, 2D lateral movement
- Add the other 3 vehicle modes with their own length/width/speed/accel from Table 2.
- Implement lateral gap calculation and lane-changing / lateral position-seeking (Algorithm 1's "Lateral movement" + position-preference logic, ref. 40 Pandey et al. — cite this as your algorithmic basis for the position-preference parameter β).
- Still no intersection — this is a heterogeneous midblock CA. Validate against mode-wise FDs (should order two-wheeler > three-wheeler > car > bus in capacity/density, matching Fig 16 shape).

### Phase 3 — Add signal + IZOI (no seepage yet)
- Implement the fixed-time signal state machine (cycle length, green/red split per approach).
- Implement IZOI as a scalar distance threshold (start with a fixed value; later replace with the field-calibrated normal-distribution-derived value per Eq 3 / Table 1).
- Implement Algorithm 2: outside IZOI → midblock rules; inside IZOI + red → decelerate/stop with no randomization; inside IZOI + green → continue.
- Validate: vehicles should form a queue that dissipates correctly on green, with reasonable saturation flow.

### Phase 4 — Full intersection assembly (4 legs, turning movements)
- Wire 4 approaches into one intersection (Fig 8a topology): each leg generates vehicles, has its own signal phase, turning-movement proportions, and deletion point after crossing.
- Implement routing (choose L/R/straight per field-observed proportions) and conflict handling at the junction (this is intentionally underspecified in the paper — see Section 11, Risk #1).

### Phase 5 — Seepage
- Implement Algorithm 3 exactly: for each vehicle near the stop line during red, check left/right/front gaps against vehicle size + safety distance (Eq 4 lateral gap, Eq 5 longitudinal gap); seep left, right, or between two vehicles, else stop.
- This should only be checked/triggered inside IZOI while signal is red (per Algorithm 1's "if vehicle is in IZOI and signal status = red" guard).
- Validate qualitatively: reproduce Fig 18's difference between seepage-off (clean parallel queue lines in x–t plot) and seepage-on (irregular, two-wheelers jump ahead of later-arriving-but-larger vehicles).

### Phase 6 — Data collection & metrics layer
- Implement the `collector` that logs, at configurable intervals: flow, density (per Eq 6–15's cell-occupancy method), per-vehicle speed/accel/headway, and full trajectories.
- This is what calibration and validation will consume — build it before calibration, not after.

### Phase 7 — Calibration
- Implement the calibration objective (Eq 16: minimize squared relative error between field and simulated flow/density at 5-min intervals over 1 hour).
- Optimizer: paper uses MATLAB's `gamultiobj` (NSGA-II variant) + `fgoalattain` hybrid over 44 parameters (11 per mode × 4 modes: randomization probs `p0`, `p_dec`, `p_bl`, safety factor `α`, lane-change prob `p_lc`, security distance, interaction headway, position preference `β`, and the 3 acceleration tiers). Practical substitute: Python `DEAP` or `pymoo` (NSGA-II is available in both) for the global step, then `scipy.optimize.minimize` (local) for refinement. This two-stage global→local pattern is worth preserving even if the exact algorithm differs.
- Keep the parameter bounds physically reasonable (probabilities in [0,1], accelerations positive, etc.) — Table 2's calibrated values are a good sanity-check reference range for your own calibration to land near.

### Phase 8 — Validation suite
- Macroscopic: two-sample t-test (field vs. simulated flow, unequal variance), q–k curve overlay, saturation flow rate comparison.
- Microscopic: Theil's U + UM/US/UC decomposition (Eq 17–20), RMSE (Eq 21), RMSPE (Eq 22) on trajectories/speed/headway, GEH (Eq 23) on volumes. Target thresholds to replicate: Theil's U < 20%, GEH < 5 (FHWA guideline).

### Phase 9 — Delay module + manual benchmarking
- Compute simulated average delay (stopped + acceleration/deceleration delay per vehicle, aggregated).
- Implement at least Indo-HCM (2017) and one Webster-based manual (e.g. Indonesian HCM 1993, structurally the simplest) as standalone formula modules, fed by the same demand/capacity/green-ratio parameters as your simulation run, to reproduce a chart like Fig 17.

### Phase 10 — Visualization & report
- x–t trajectory plots (Fig 14/18 style), speed/headway/acceleration comparison plots (Fig 12/13 style), FD plots (Fig 10/16 style), delay bar chart (Fig 17 style).
- Package this as a short internal report — this becomes the "replication" writeup that motivates your novel problem statement.

**Do not skip phases 1–2 to jump straight to the full intersection.** The paper itself builds up this way (midblock rules → IZOI modification → seepage addition), and debugging a 2D heterogeneous CA is much easier one behavior at a time.

---

## 4. Algorithms to implement (explicit checklist, paper-numbered)

- **Algorithm 1 (Vehicle model):** fixed properties (dims, max/min speed & accel, ID) at init; public properties (randomization params, lane-change prob, safety gap, position preference) updated each step; NaSch-style accel/decel/randomize/brake-light/lateral-move/position-specific-lane-change pipeline, per step, per vehicle.
- **Algorithm 2 (IZOI rules):** `if position < IZOI: decelerate at field-observed rate elif position > IZOI: continue as midblock`.
- **Algorithm 3 (Seepage):** for each vehicle, in order, check left gap → right gap → front-vehicle lateral spread gap → else reduce speed and stop. Gate this on IZOI + red signal.
- **Eq 3 (IZOI value):** IZOI = μ ± z·σ/√N from field GPS deceleration-onset data (95% CI). You'll need your own μ, σ, N (see Section 5) or a reasonable literature-sourced placeholder (~150–200 m per paper's Table 1, mode-dependent) if you can't collect fresh GPS data immediately.
- **Eq 4–5 (lateral/longitudinal seepage gaps):** lateral gap = min(d4, d3); longitudinal gap = min(d1, d2), per Fig 6's 3-vehicle geometry.
- **Eq 6–15 (density/flow via cell occupancy):** density = occupied cells ÷ total cells in section, converted to veh/km via vehicle footprint in cells.
- **Eq 16 (calibration objective):** sum of squared [(field_flow − sim_flow)/(field_density − sim_density)] across 5-min bins.
- **Eq 17–20 (Theil's U + decomposition), Eq 21 (RMSE), Eq 22 (RMSPE), Eq 23 (GEH):** implement as pure statistics functions operating on paired (observed, simulated) arrays — these are reusable outside this project too, worth writing as a small standalone stats module.

---

## 5. Data you need, and where to get it

The paper's own data (Delhi + Mumbai video, extracted via a MATLAB tool called MTraDE, plus GPS-logged IZOI trajectories) is **not publicly released** — the paper's Data Accessibility Statement says it's available from the corresponding author "on reasonable request" only. Since that's not guaranteed, plan around public substitutes. All of these are real, currently-existing sources (checked today):

### 5.1 Primary recommendation — Kanagaraj et al. (2015) mixed traffic trajectory dataset
- **What it is:** Vehicle trajectory data extracted from video on an urban midblock road section in Chennai, India — heterogeneous, non-lane-based traffic, exactly the setting this paper targets. Directly cited as the standard open dataset in this exact sub-field by multiple recent (2024–2025) IIT Madras papers on non-lane-based traffic.
- **Direct download (no signup):**
  - Part 1 (2:45–3:00 PM): `https://toledo.net.technion.ac.il/files/2014/10/ChennaiTrajectoryData2.45-3.00PM.xlsx`
  - Part 2 (3:00–3:15 PM): `https://toledo.net.technion.ac.il/files/2014/10/ChennaiTrajectoryData3.00-3.15PM.xlsx`
  - Data description PDF: `https://toledo.net.technion.ac.il/files/2014/10/TrajectoryDataDescription.pdf`
  - Landing page: `https://toledo.net.technion.ac.il/mixed-traffic-trajectory-data/`
- **Caveat:** this is a **midblock** section, not a signalized intersection. Use it to calibrate car-following/lateral-gap/seepage-adjacent parameters (Phases 1–2), not the IZOI/signal logic directly.
- **Citation:** Kanagaraj, V., Asaithambi, G., Toledo, T., & Lee, T.-C. (2015). Trajectory Data and Flow Characteristics of Mixed Traffic. *TRR*, 2491, 1–11.

### 5.2 Intersection-adjacent — UAV microscopic vehicle trajectory (MVT) datasets, IIT Delhi
- **What it is:** Openly released UAV/drone-collected trajectory datasets for heterogeneous, area-based urban traffic at **six midblock locations in the Delhi NCR**, published by Yawar Ali, K. Ramachandra Rao (co-author of the paper you're implementing), Ashish Bhaskar & Niladri Chatterjee. 30 fps, includes speed and longitudinal/lateral acceleration per vehicle, vehicle classification. ~3,005 processed vehicle trajectories.
- **Why it matters:** same senior author/research group as your base paper — parameter ranges and driver-behavior assumptions should be broadly consistent with what you're replicating.
- **How to get it:** paper is on arXiv (`arxiv.org/abs/2512.11898` — search "Microscopic Vehicle Trajectory Datasets from UAV-collected Video for Heterogeneous, Area-Based Urban Traffic"); check the paper's data-availability section for the actual hosting link (likely Mendeley Data, Zenodo, or a TRIPC/IIT Delhi page) before assuming direct download — confirm current link when you sit down to fetch it, since exact hosting can change.

### 5.3 Dense/heterogeneous video with detections — TRAF dataset (for building your OWN trajectory extractor)
- **What it is:** 60 video sequences of dense, heterogeneous Asian (India/China) traffic — cars, buses, scooters, rickshaws, bicycles, pedestrians — with 2D bounding box + agent-type ground truth. Built for trajectory prediction (TraPHic, CVPR 2019) but perfectly usable as raw footage for you to run your own detector/tracker on and extract trajectories in the exact format your CA calibration needs.
- **Links:** dataset page `https://gamma.umd.edu/researchdirections/autonomousdriving/trafdataset/`; companion code/tooling `https://github.com/rohanchandra30/TrackNPred` (includes a detection+tracking+prediction pipeline you can partially reuse or just reference for structure).
- **Why relevant to you specifically:** you already have YOLOv8 pipeline experience (Atrio project). Running YOLOv8 + a tracker (ByteTrack/DeepSORT, or `ultralytics`' built-in `track()` mode) on a couple of TRAF clips (or your own phone/drone footage of an Indian intersection) is a very feasible way to generate your *own* field trajectory + headway + IZOI dataset instead of depending on someone else's, and it directly mirrors what the paper's MTraDE tool was doing.

### 5.4 Vehicle detector training data (Indian traffic, if you build your own extractor)
- **DATS_2022:** Indian traffic object-detection image dataset (rural + urban), XML/VOC-style annotations, published via PMC/open access. Useful if your existing detector doesn't classify Indian-specific classes well (auto-rickshaw, cycle-rickshaw, etc.) and you need to fine-tune. Search "DATS_2022 Indian traffic dataset" — hosted with the PMC article `pmc.ncbi.nlm.nih.gov/articles/PMC9309657/`; check that article's data-availability section for the current Mendeley/IEEE DataPort link.

### 5.5 Author's own seepage demonstration video
- The paper cites its own seepage field video: `https://www.youtube.com/watch?v=FHGkGehEC2w` (Singh, M.K., "Seepage Behavior"). Useful as a **qualitative reference clip** to sanity-check your Fig-18-style visualizations against, and as one more source clip to run a detector/tracker over. Download with `yt-dlp` if you want to extract frames locally (respect YouTube ToS — for personal research use only).

### 5.6 Benchmark-only (not this traffic regime, use only for sanity-checking core CA engine)
- **NGSIM** (US freeway trajectory data) — lane-based, homogeneous, NOT representative of this paper's traffic, but useful in Phase 1 only, to confirm your base NaSch engine produces textbook triangular FDs before you add heterogeneity/non-lane-based behavior.

### 5.7 If you'd rather collect fresh field data yourselves
Given you're at IIT BHU Varanasi, the cheapest path to a paper-faithful dataset is: pick 1–2 signalized intersections on campus-adjacent roads, record ~1–2 hours of video (phone on a tripod/overbridge, or a low-cost drone if TRIPC/your dept has one), and:
1. Run YOLOv8 + ByteTrack for per-vehicle bounding boxes/tracks.
2. Homography-correct pixel coordinates to real-world meters (need 4+ known ground-truth points in the frame, e.g. lane markings/zebra crossing corners).
3. Derive speed/accel by finite-differencing smoothed positions (paper uses locally-weighted regression, per Toledo et al.).
4. Manually tag left/right/straight and vehicle class for a validation subset to check your detector.
This gives you IZOI-eligible GPS-style data (Eq 1–3) AND your own calibration/validation set, which is strictly better than reusing someone else's midblock dataset for an intersection paper.

---

## 6. Calibration & Validation Plan (concrete steps)

1. Split your chosen dataset (own-collected or public) into **calibration** (e.g. day 1–2) and **validation** (day 3, or a held-out time window) sets, mirroring the paper's Delhi (calibration) / Mumbai (validation) split logic — different site or different day, not the same slice of data.
2. Extract, per 5-min bin: flow (veh/hr) and density (veh/km) for calibration target.
3. Run calibration optimizer (Phase 7) until Eq 16 objective plateaus; log convergence curve.
4. Freeze parameters, run fresh simulation replications (different random seed) on the validation split's conditions (headway distribution, mode mix, IZOI, cycle length).
5. Run the full validation stats suite (Phase 8) and record all numbers in a results table mirroring the paper's Tables 3–4 and Figure 15.
6. Only once GEH < 5 and Theil's U < 20% (or you understand and can explain why not) do you move to delay/manual benchmarking (Phase 9) and seepage visualization (Phase 5 output, Phase 10).

---

## 7. Tech stack recommendation

- **Language:** Python for the whole simulator. Reasons: you need fast iteration on stochastic rules, a NumPy-vectorizable grid, and access to `pymoo`/`DEAP` (GA), `scipy.stats` (Theil's U components are trivial to hand-roll, t-test is `scipy.stats.ttest_ind`), `pandas` for the flow/density/trajectory bookkeeping, and `matplotlib`/`plotly` for all the Fig 10–18-style plots. Your Java DSA workflow is a separate track — no need to force this into Java.
- **Grid representation:** don't naively loop cell-by-cell in Python for a 20,000-cell/km × 4-leg grid at per-second resolution — that will be slow. Recommend an **agent-list + spatial-index** representation instead (each vehicle stores its own continuous or fine-grained-cell (x,y); use a coarse spatial hash or `scipy.spatial.cKDTree` for neighbor/gap queries) rather than a dense 2D occupancy array. This is functionally equivalent to the paper's CA (same cell size 0.5m×0.7m, same discrete rules) but far more tractable to implement/debug/vectorize in Python.
- **Optimization:** `pymoo`'s NSGA-II for the global multi-objective step (closest open-source analog to MATLAB's `gamultiobj`), then `scipy.optimize.minimize` (Nelder-Mead or L-BFGS-B) for local refinement — mirrors the paper's hybrid GA + goal-attainment approach.
- **Testing:** `pytest` with unit tests per module (gap calc, IZOI switch, seepage decision, density/flow conversion) using small hand-computable fixtures before trusting any full-scale run.
- **Config:** keep road geometry, signal timing, mode mix, and calibration bounds in a YAML/JSON config file per intersection/scenario — you'll want to run many scenario variants once the base engine works, especially once you move to your own novel problem statement.

---

## 8. Suggested repo structure

```
ca-seepage-sim/
  README.md
  plan.md                      <- this file
  configs/
    intersection_default.yaml
  data/
    raw/                       <- downloaded datasets (gitignored)
    processed/                 <- cleaned trajectory csvs
  src/
    core/
      vehicle.py
      grid.py
      gaps.py
      motion.py
      lane_change.py
    intersection/
      signal.py
      izoi.py
      seepage.py
      routing.py
      intersection.py
    sim/
      generator.py
      sim_loop.py
      collector.py
    metrics/
      density_flow.py
      theils_u.py
      geh.py
      rmse_rmspe.py
    calibration/
      objective.py
      optimizer.py
    delay/
      simulated_delay.py
      manuals/
        indo_hcm.py
        hcm2010.py
        indonesian_hcm.py
    viz/
      trajectories.py
      fundamental_diagrams.py
      delay_chart.py
  scripts/
    download_data.py           <- pulls Section 5 datasets
    extract_trajectories_yolo.py  <- optional: your own video -> trajectory pipeline
    run_calibration.py
    run_validation.py
    run_full_replication.py
  tests/
    test_gaps.py
    test_izoi.py
    test_seepage.py
    test_metrics.py
  notebooks/
    01_explore_raw_data.ipynb
    02_phase1_single_lane_sanity_check.ipynb
    03_phase5_seepage_trajectories.ipynb
```

---

## 9. Deliverables checklist per phase (what "done" means)

- [ ] Phase 0: repo scaffolded, one dataset downloaded and loaded into a pandas DataFrame.
- [ ] Phase 1: single-lane single-mode CA producing a triangular FD.
- [ ] Phase 2: 4-mode 2D CA producing mode-ordered FDs (Fig 16 shape).
- [ ] Phase 3: signal + IZOI producing correct queue formation/dissipation.
- [ ] Phase 4: full 4-leg intersection with turning movements running end-to-end.
- [ ] Phase 5: seepage on/off toggle producing visibly different x–t trajectory plots.
- [ ] Phase 6: collector producing flow/density/speed/headway/trajectory logs on demand.
- [ ] Phase 7: calibration run converges, parameters land in physically sane ranges near Table 2.
- [ ] Phase 8: validation stats computed and tabulated (GEH, Theil's U, RMSE, RMSPE, t-test).
- [ ] Phase 9: simulated delay computed + compared against ≥2 manual formulas, chart produced.
- [ ] Phase 10: final report/notebook with all figures, ready to discuss with Dr. Kashyap/teammate.

---

## 10. After replication: candidate novel problem statements

Once the replication above is solid, revisit your meeting notes' three directions with a working simulator in hand — you'll be much better positioned to pick one:

1. **Order-of-vehicles under seepage (your own framing):** instrument the simulator to log FIFO-violation events — i.e., for each vehicle pair, whether departure order at the stop line matches arrival order at the back of queue. Quantify how seepage-driven reordering scales with two-wheeler proportion, IZOI length, and cycle length. This directly operationalizes the open question from your meeting notes ("how does the order of vehicles change due to seepage?") and is a clean, novel, quantifiable contribution the base paper doesn't address.
2. **Calibration-focused contribution:** the paper flags "calibration work is understudied" in this space. A comparison of calibration strategies (their GA+goal-attainment vs. Bayesian optimization vs. simulated annealing vs. surrogate-model-based calibration) on the same seepage CA, measured by convergence speed + parameter stability across sites, is a legitimate methods paper.
3. **Signal-timing optimization under seepage-aware delay:** use your validated simulator as the environment for an RL or classical optimization agent that sets cycle length/green split to minimize delay/emissions *given* seepage (something the manuals in Table 5 structurally can't do, since none of them model seepage capacity gain directly) — ties nicely into your existing RL/agentic-systems interests.
4. **Two-wheeler-specific safety angle:** combine seepage trajectories with a simple conflict/near-miss detector (e.g. SSAM-style post-encroachment time) to quantify the safety cost of the capacity benefit seepage provides — addresses the paper's own stated concern that seepage "can affect safety" but is never measured in the paper itself.

Bring the working replication + this shortlist to your next meeting with Dr. Kashyap and Aditya rather than deciding in isolation — the choice should factor in what's publishable in your remaining internship timeline and what compute/data you'll realistically have.

---

## 11. Risks / open questions to flag early (don't discover these at Phase 8)

1. **Conflict resolution at the junction itself is underspecified in the paper.** Figure 1/8 describe approach, IZOI, and stop-line behavior in detail, but not exactly how simultaneous-green conflicting movements (e.g. opposing right-turns) resolve once inside the intersection box. You'll need to make and document your own reasonable assumption (e.g. right-turning vehicles yield to opposing through traffic) — flag this explicitly as a modeling choice in your writeup.
2. **IZOI value depends on GPS deceleration data you may not have.** Decide early whether you're collecting your own (Section 5.7) or using the paper's reported ranges (Table 1: ~99–214 m depending on mode) as fixed literature values. Using literature values is fine for a first replication pass but weakens any calibration claims.
3. **Exact GA/goal-attainment MATLAB behavior won't be bit-identical to any open-source substitute.** Don't chase exact parameter-value replication (Table 2's numbers) — chase *distributional/behavioral* replication (correct FD ordering, correct queue dynamics, correct seepage pattern). Say this explicitly in any report to avoid over-claiming.
4. **Density/flow via cell-occupancy (Eq 6–15) requires you to fix cell size and vehicle footprints consistently everywhere** (grid, gap checks, seepage checks, density calc) — a common bug source is having two different cell-size assumptions in different modules.
5. **Performance:** at full 4-leg, 4-mode, 1-hour, 1-second-resolution scale this is a lot of agents × steps. Profile early (Phase 3–4), not after Phase 7 when calibration needs hundreds of runs.