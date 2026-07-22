# START HERE — How to use these prompt files

You  will receive 11 files, one per phase: `phase00_scaffolding.md`
through `phase10_visualization_report.md`. **Do them in order.** Do not skip ahead
even if a later phase looks easy — each phase's tests are the safety net for the
next one.

Paste ONE phase file per session/turn into the coding agent. Each phase file is
self-contained: it restates what must already exist from prior phases, so you
don't need to re-paste earlier prompts.

---

## Ground rules that apply to EVERY phase (do not restate these each time, just follow them)

1. **Repo root is `ca-seepage-sim/`.** Always work inside it. If it doesn't exist yet, Phase 0 creates it.
2. **Python 3.11+, virtual env named `.venv`.** Use `pip install` inside the venv, and freeze
   dependencies to `requirements.txt` after every phase (append, don't blindly overwrite).
3. **Every phase ends with passing tests.** Use `pytest`. Do not mark a phase "done" until
   `pytest -q` exits 0. If a test fails, fix the code — do not delete or weaken the test to
   make it pass.
4. **Every phase ends with a short `PHASE_REPORT.md` entry.** Append (don't overwrite) a
   section to `ca-seepage-sim/PHASE_REPORT.md` titled `## Phase N — <name>` containing:
   - What was implemented (bullet list of files touched)
   - Test results (paste `pytest -q` output)
   - Any assumption or simplification you made that deviates from the spec, and why
   - Any TODO you deferred to a later phase
5. **No network calls inside simulation/library code.** Data downloading lives only in
   `scripts/download_data.py`. Core simulator modules (`src/**`) must run fully offline.
6. **If a dataset URL is dead or download fails:** do NOT block. Generate a small synthetic
   trajectory dataset with the same column schema (documented in each phase that needs data)
   using a fixed random seed, save it to `data/processed/`, and clearly log/flag in
   `PHASE_REPORT.md` that synthetic data was used as a fallback. Real data can be swapped in later
   without touching simulator code, because the simulator only ever reads from `data/processed/`.
7. **Config, not hardcoding.** Any number that is a physical/behavioral parameter (cell size,
   max speed, IZOI distance, cycle length, calibration bounds, etc.) belongs in a YAML file
   under `configs/`, never hardcoded inside a function body.
8. **Type hints + docstrings on every public function/class.** This is non-negotiable —
   it's what keeps a "mediocre" agent's own later output consistent with itself.
9. **Small, testable units.** If a phase prompt asks for a module with 3 functions, write
   3 functions with 3 separate unit tests, not one monolithic function.
10. **Never invent paper numbers you don't have.** If a target value from the base paper isn't
    directly available to you (you don't have the paper's raw data), say so explicitly in
    `PHASE_REPORT.md` rather than fabricating a number that "looks right."
11. **Commit after every phase**: `git add -A && git commit -m "Phase N: <short description>"`.
    If git isn't initialized yet, Phase 0 handles that.
12. **Ask nothing mid-phase.** These prompts are written to be fully self-contained. If you hit
    a genuine ambiguity not covered by the prompt, make the most conservative reasonable choice,
    document it in `PHASE_REPORT.md` under "Assumptions," and keep going. Do not stop and wait.

---

## Reference doc

All 11 phase files implement `plan.md` (the master research/implementation plan for
replicating Singh & Ramachandra Rao (2023), *"Simulation of Signalized Intersection with
Non-Lane-Based Heterogeneous Traffic Conditions Using Cellular Automata,"* TRR,
DOI: 10.1177/03611981231211317). Keep `plan.md` in the repo root — you may be asked to
cross-check specific equation/algorithm numbers against it.

## Order of files

| File | Builds |
|---|---|
| `phase00_scaffolding.md` | repo skeleton, config system, first dataset loaded |
| `phase01_single_lane_ca.md` | single-mode NaSch CA, midblock, sanity FD |
| `phase02_multimode_2d.md` | 4 vehicle modes, lateral movement, mode-ordered FDs |
| `phase03_signal_izoi.md` | traffic signal + IZOI behavior switch |
| `phase04_full_intersection.md` | 4-leg intersection, routing/turning |
| `phase05_seepage.md` | Algorithm 3 seepage behavior |
| `phase06_data_collection.md` | metrics/logging layer (flow, density, trajectories) |
| `phase07_calibration.md` | GA/NSGA-II parameter calibration |
| `phase08_validation.md` | GEH, Theil's U, RMSE, RMSPE, t-test |
| `phase09_delay_manuals.md` | simulated delay + HCM-style manual formulas |
| `phase10_visualization_report.md` | final plots + report notebook |

Start with `phase00_scaffolding.md`.
