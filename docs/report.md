# Project Context — What We've Actually Built (Plain-Language Version)

*A self-contained explainer, written so you (or anyone else) can read it later without needing to remember all the back-and-forth that got us here.*

---

## 1. What is this project, in one paragraph?

We're rebuilding, from scratch, the traffic simulation described in a real research paper (Singh & Ramachandra Rao, 2023) about how Indian-style traffic behaves at a signalized intersection — specifically the messy, non-lane-based mix of two-wheelers, autos, cars, and buses. The paper's headline behavior is **seepage**: when traffic is stopped at a red light, small vehicles don't just wait in line — they squeeze sideways through gaps between bigger stopped vehicles to get closer to the front. Our job was first to rebuild this simulation faithfully and test it against real data, and only *after* that works, use it to answer our own original question: **does seepage actually change the order in which vehicles arrive vs. leave the intersection?**

---

## 2. How the simulation actually works (in plain terms)

Think of the road as a grid of tiny cells, like graph paper. Each vehicle occupies a few cells (a bus takes up more cells than a two-wheeler). Every "tick" of the simulation (roughly one second of real time), every vehicle looks at what's around it and decides: speed up, slow down, or move sideways. Do this thousands of times with hundreds of vehicles, and you get a working miniature traffic system you can experiment on — try different signal timings, different vehicle mixes, different behaviors — without needing to close down a real road.

We built this in strict stages (10 "phases"), because if the basic vehicle-movement rules have a bug, everything built on top of it — the intersection, the traffic signal, the seepage behavior — would be quietly wrong too. So each phase had to prove itself correct before we moved to the next one.

---

## 3. What's been built so far (phase by phase)

### Phase 0 — Getting real data
Before writing any traffic logic, we got our hands on **real vehicle trajectory data** — actual recorded positions and speeds of real vehicles on a real Indian road (a published dataset from Chennai, by Kanagaraj et al., 2015). This is what we calibrate and check our simulation against later, instead of just guessing numbers.

### Phase 1 — The basic movement engine
Built the core rule for how a single vehicle moves: speed up if the road ahead is clear, slow down if there's a vehicle close ahead, and occasionally brake randomly for no reason (this mimics real distracted/cautious driving and is what makes traffic jams form naturally in real life too). Tested this with just one type of vehicle (cars) on a straight road, no intersection yet — basically making sure the "physics engine" itself works before adding any complexity.

*Figures:* `phase1_diagnostic_fd.png` and `phase1_open_diagnostic_fd.png` — these show that if you pack vehicles at different densities, our simulation reproduces the classic "flow rises, peaks, then falls" traffic pattern that real traffic theory predicts. This is the most basic sanity check possible, and it passed.

### Phase 2 — Adding all 4 vehicle types + side-to-side movement
Added three-wheelers, buses, and two-wheelers, each with their own size and speed. Also added **non-lane-based movement** — meaning vehicles aren't stuck in fixed lanes, they can drift sideways within the road width, which is how Indian traffic actually behaves. Confirmed that smaller/faster vehicles (two-wheelers) can move more traffic through a given space than bigger/slower ones (buses) — exactly what the paper predicts.

*Figure:* `phase2_diagnostic_fd.png` — same "flow vs. density" check as Phase 1, but now for all 4 vehicle types together, confirming the same correct pattern holds.

### Phase 3 — Adding the traffic signal
Added a real red/green traffic light with real timing pulled from the paper (130-second cycle, 30 seconds of green). Also added the concept of an **"Influence Zone"** — a distance from the stop line where vehicles start driving differently because they can see the signal (braking earlier, more cautiously). Confirmed vehicles correctly form a queue during red and clear it during green.

*Figure:* `phase3_queue_formation.png` — a plot of vehicle positions over time, colored by vehicle type, showing the queue building up during red (flat horizontal lines = stopped vehicles) and discharging during green (upward-sloping lines = moving again).

### Phase 4 — The full intersection, all 4 directions at once
This was the hardest phase. Instead of one road, we now have a real 4-way intersection — North, South, East, West all feeding in, with vehicles able to go straight, turn left, or turn right. This required solving real conflict problems: what happens when two vehicles from different directions both want the same space at the same time? We found and fixed several serious bugs here (vehicles getting permanently stuck, vehicles disappearing instead of properly passing through, some vehicles blocking others that shouldn't have been blocked) before this was considered solid.

*Figures:* `phase4_combined_view.png` and `phase4_full_intersection_trajectories...` (there appear to be two versions of this saved — worth checking which is the final clean one) — these show vehicles from all 4 directions moving through the intersection, including turning vehicles, without colliding.

### Phase 5 — Seepage (the actual novel behavior)
This is the paper's centerpiece and the reason this whole project exists. We implemented the exact rule: when a small vehicle (two-wheeler or three-wheeler) is stopped at a red light, it checks — is there a gap to my left? To my right? A diagonal gap between two vehicles ahead? If yes, squeeze through. Cars and buses never do this (they're too big). We also built a way to **measure how much this actually changes vehicle order** — see Section 5 below, this directly answers your question.

*Figure:* `phase5_seepage_trajectories.png` — a two-panel comparison: left panel shows normal queueing (seepage turned off), right panel shows the same scenario with seepage turned on. You should be able to see two-wheelers visibly cutting ahead of larger vehicles in the right panel that don't cut ahead in the left panel.

### Phase 6 — Making the data trustworthy
Not a new behavior — this phase built the proper "instrumentation": a clean, consistent way to log every vehicle's position, speed, and status at every timestep, and to calculate traffic flow and density the exact way the paper's equations specify. We also found and fixed a subtle bug where our flow-counting was slightly undercounting vehicles at certain measurement boundaries.

*No dedicated figure* — this phase was plumbing/infrastructure, not a new visual result. (If you expected a figure here and don't see one in the folder, that's expected — Phase 6 focused on making Phase 2's earlier flow-check formula more precise, not producing a new plot.)

### Phase 7 — Calibration (tuning the model against real data)
Took our real Chennai trajectory data and tried to automatically tune the model's driver-behavior settings (how cautious drivers are, how much they randomly brake, how often they change lateral position) to best match what real traffic actually looks like. We found and fixed two real bugs in this process (a mismatch in traffic volume assumptions, and a measurement-point issue). The honest final result: **our tuned parameters didn't clearly beat the paper's own published default values** — most likely because our real dataset is from an open road, not an actual intersection, so it can't perfectly tune intersection-specific behavior. We're reporting this plainly rather than hiding it — it's a real and useful finding, not a failure.

*Figures:* `phase7_convergence.png` (shows the tuning process improving over time, then leveling off) and `phase7_fd_comparison.png` (shows our simulation's traffic pattern compared side-by-side against the real field data).

### Phase 8 — Validation (in progress right now)
Currently running formal statistical tests comparing our simulation's output against real field data it *wasn't* tuned on (a fair, honest test) — using standard traffic-engineering accuracy metrics. Not finished yet, so no figures for this phase exist in the folder yet.

### Phase 9 — Delay comparison (not started)
Will estimate how much extra time vehicles lose at the intersection because of the signal, and compare that against standard published traffic-engineering formulas (the kind real traffic engineers use to design intersections).

### Phase 10 — Final write-up (not started)
Will pull everything into one clean, final report with all figures and honest conclusions.

---

## 4. Figures currently in your `figures/` folder — quick reference

| Figure file | Which phase | What it shows |
|---|---|---|
| `phase1_diagnostic_fd.png` | 1 | Basic traffic physics sanity check (single vehicle type) |
| `phase1_open_diagnostic_fd.png` | 1 | Same check, but on an open road (no artificial boundary) |
| `phase2_diagnostic_fd.png` | 2 | Same sanity check, now with all 4 vehicle types |
| `phase3_queue_formation.png` | 3 | Vehicles queueing at red, clearing at green |
| `phase4_combined_view.png` | 4 | Full 4-way intersection, all directions overlaid |
| `phase4_full_intersection_traject...` (x2) | 4 | Turning vehicle paths through the intersection (two saved versions — check which is final) |
| `phase5_seepage_trajectories.png` | 5 | Seepage on vs. off, side by side |
| `phase7_convergence.png` | 7 | How the auto-tuning process progressed over time |
| `phase7_fd_comparison.png` | 7 | Our simulation vs. real field data, side by side |

**Note:** a couple of earlier figures mentioned during development (e.g. Phase 0's initial data-exploration plots, and Phase 2's mode-mix flow comparison) aren't showing up in this specific listing — they may be saved under slightly different filenames or in a different subfolder. Worth a quick check if you need them for a presentation.

---

## 5. Your specific question: have we actually tagged vehicles and tracked their order?

**Yes — this has been built, and it's one of the more solid results so far.**

Here's exactly what exists:

- **Every single vehicle gets a unique ID number** the moment it's created (as far back as Phase 1). This ID stays with it for its entire time in the simulation — every log entry, every timestep, records which specific vehicle it's about.
- **Every vehicle's arrival time is recorded** — when it joined the back of a queue.
- **Every vehicle's departure/crossing time is recorded** — when it actually passed the stop line.
- In Phase 5, we specifically built an **order-comparison tool**: for any two vehicles that were both waiting in the same queue, it checks whether the one that arrived first also *left* first. If vehicle B arrived after vehicle A but leaves before vehicle A, that's counted as an "order-reversal" (an overtake event).

Using this, we already have a real measured result: in a test run, **seepage was directly responsible for about 6.7% of all order-reversal events** (36 out of roughly 537). Interestingly, the *majority* of order reversals (around 90%) came from something else entirely — plain old speed differences (a two-wheeler naturally driving faster than a bus, even with no seepage involved, just from normal free-flow driving before either vehicle reaches the queue).

**One thing worth double-checking with your teammate:** Krish mentioned to Dr. Das that "Kendall tau distance" is being used for order-tracking. What we've actually built and verified so far is a simpler **arrival-vs-departure overtake-count** method, not literally the Kendall tau statistic (which is a specific mathematical way of measuring how "shuffled" two orderings are relative to each other). These aren't necessarily in conflict — Kendall tau might be a next step being built on top of the same underlying vehicle-ID and arrival/departure data we already have — but it's worth syncing with Krish so you're both describing the same thing to Dr. Das, or being clear if there are two related-but-different measurements in play.

---

## 6. The big findings so far, in plain language

1. **The simulation's basic physics is correct** — verified two separate ways, both showing the traffic pattern real theory predicts.
2. **Smaller vehicles really do move more efficiently through space** in our model, matching the paper's claim, in the right order (two-wheeler > three-wheeler > car > bus).
3. **Seepage works and is measurable** — it's implemented correctly, doesn't cause any crashes/collisions even under heavy traffic, and we can now put an actual number on how much it reorders vehicles (about 6.7% of reordering events, with the rest coming from ordinary speed differences).
4. **Tuning the model against real data didn't clearly help** — an honest, slightly disappointing but genuinely useful result, most likely because we only have open-road data, not real intersection data, to tune against.

---

## 7. What's actually left to do

- **Finish Phase 8** — formal accuracy testing against real data.
- **Phase 9** — compare our simulation's delay estimates against standard textbook traffic-engineering formulas.
- **Phase 10** — final consolidated report with all results and honest limitations.
- **Then, the real research question** — once the replication is fully validated, pick one of these to actually contribute something new:
  1. Dig deeper into the seepage-reordering result above (this is the most ready-to-go option, since the measurement tool already exists).
  2. Compare different ways of tuning the model (since Phase 7 showed our current tuning approach has limits).
  3. Use the simulator to test smarter signal-timing strategies that account for seepage.
  4. Study whether seepage's efficiency benefit comes with a safety cost (near-misses, etc.).

---

## 8. Things to be upfront about (limitations)

- We don't have real intersection field data (the paper's own data isn't public) — only open-road data, which limits how much we could fine-tune intersection-specific behavior.
- One specific number (how early a two-wheeler starts reacting to a red light) isn't in the paper at all — we used a reasonable estimate instead of a measured value.
- How exactly two vehicles turning at the same time resolve their conflict inside the intersection isn't fully specified by the paper either — we made a reasonable, clearly-documented assumption (through traffic gets priority over turning traffic).
- A vehicle that turns currently "disappears" once it clears the intersection box rather than continuing to be tracked on its new road — a simplification we may need to revisit depending on what Phase 9 shows.

---

*This document reflects everything built and verified through Phase 7, plus Phase 8 in progress. Update it as Phases 8–10 wrap up.*
