# PHASE 10 — Visualization & Final Report

## Before you start
Follow `00_START_HERE.md`. Requires Phases 0-9 all complete, all tests passing, and
`PHASE_REPORT.md` containing sections for every prior phase.

## Goal of this phase
This is a consolidation phase, not a new-feature phase: polish and assemble the figures
already produced across Phases 1-9 into a coherent final notebook/report package that
constitutes the "replication is done" deliverable, per plan.md §3 Phase 10 and §9's
deliverables checklist.

## Steps

### 1. `src/viz/` — refactor, don't reinvent
Move the plotting code that's currently scattered inline across the various phase notebooks
into proper reusable functions:
- `src/viz/trajectories.py`: `plot_xt_trajectories(df, color_by="mode", ax=None) -> Axes`
  (generalizes the Phase 3/5 space-time plotting code).
- `src/viz/fundamental_diagrams.py`: `plot_fd_by_mode(flow_density_df, ax=None) -> Axes`
  (generalizes Phase 2/6/7's FD plotting).
- `src/viz/delay_chart.py`: `plot_delay_comparison(delay_df, ax=None) -> Axes` (generalizes
  Phase 9's bar chart).
Each function must accept an optional `ax` (matplotlib Axes) parameter so they can be
composed into multi-panel figures here, rather than each producing its own standalone full-
figure PNG as earlier phases did. Add minimal smoke tests (`tests/test_viz.py`) that just
assert each function runs without raising on a small synthetic DataFrame fixture and returns
an Axes object — these are not visual-correctness tests, just "doesn't crash" tests.

### 2. `notebooks/03_phase5_seepage_trajectories.ipynb` → rename/expand into
`notebooks/04_final_replication_report.ipynb`, structured as a narrative document with
these sections (use markdown cells for narrative, code cells calling the `src/viz/` functions
— do not re-derive plotting logic inline in the notebook, call the library functions):

1. **Intro**: 2-3 sentences restating the paper being replicated (title, authors, DOI) and
   the scope of this replication (cite plan.md §1's acceptance criteria list).
2. **Data used**: state explicitly which dataset(s) were actually used (real Kanagaraj data
   vs. synthetic fallback — pull this straight from what Phase 0/8's `PHASE_REPORT.md`
   entries recorded, don't re-derive).
3. **Core engine validation** (Phase 1-2): embed `phase1_fundamental_diagram.png` and
   `phase2_fundamental_diagrams_by_mode.png`, one paragraph of interpretation each.
4. **Signal + IZOI + full intersection** (Phase 3-4): embed the queue-formation and
   4-leg trajectory plots, one paragraph each.
5. **Seepage** (Phase 5): embed the two-panel seepage on/off comparison, report the
   FIFO-violation count/rate computed in Phase 5, one paragraph connecting this to the
   teammate meeting notes' original open question ("how does the order of vehicles change
   due to seepage") — frame this explicitly as the seed of the "after replication" novel
   direction (plan.md §10), not as a completed research contribution yet.
6. **Calibration & Validation** (Phase 7-8): embed the convergence plot and the macro/micro
   validation plots, and a results table (GEH, Theil's U + decomposition, RMSE, RMSPE,
   t-test p-value) rendered directly from `data/processed/validation_results.csv` — read the
   CSV in the notebook, do not hand-copy numbers.
7. **Delay vs. manuals** (Phase 9): embed the delay comparison chart and results table from
   `data/processed/delay_comparison.csv`.
8. **Honest limitations section** (required, do not skip): explicitly list, pulling directly
   from what each phase's `PHASE_REPORT.md` entry already flagged —
   - real vs. synthetic data used, and what that implies for how much the validation numbers
     should be trusted (plan.md §11 risk #2)
   - the conflict-resolution assumption made at the junction box (plan.md §11 risk #1)
   - single-objective GA used instead of the paper's multi-objective `gamultiobj` +
     goal-attainment hybrid (plan.md §11 risk #3)
   - which manual-formula constants were defaulted/assumed rather than sourced from the
     actual Indo-HCM/Indonesian-HCM manuals
   - any GEH/Theil's-U targets that were NOT met, and the most likely reason why
9. **Next steps**: list plan.md §10's 4 candidate novel-problem-statement directions verbatim
   (order-of-vehicles under seepage / calibration methods comparison / signal optimization
   under seepage-aware delay / two-wheeler safety angle), each with one sentence noting how
   much of the groundwork this replication already provides for it (e.g. direction #1 already
   has the `seepage_action` logging and FIFO-violation counter built in Phase 5).

### 3. `README.md` (repo root) — write a real one now
Replace whatever placeholder existed since Phase 0 with: project title, one-paragraph
description, the paper citation, how to set up the venv, how to run
`scripts/download_data.py`, `scripts/run_calibration.py`, `scripts/run_validation.py`,
`scripts/run_delay_comparison.py` in order, and a pointer to
`notebooks/04_final_replication_report.ipynb` as the main results document. Include the repo
structure tree (you can copy plan.md §8's tree and update it to match what actually got
built, noting any files that ended up named/organized differently than planned).

## Acceptance criteria
- [ ] `pytest -q` passes (full suite, all phases).
- [ ] `notebooks/04_final_replication_report.ipynb` runs top-to-bottom without errors and
      renders all 9 sections above with real embedded figures and real numbers pulled from
      the CSVs (not hand-typed).
- [ ] `README.md` is complete and someone with a fresh clone could follow it to reproduce the
      whole pipeline.
- [ ] `PHASE_REPORT.md` has a final `## Phase 10 — Wrap-up` section explicitly stating the
      overall status against plan.md §9's full deliverables checklist (paste that checklist
      with each box checked or explicitly marked "not met, because...").
- [ ] Final git commit made, e.g. `git commit -m "Phase 10: replication complete"`, and
      confirm `git log --oneline` shows 11+ commits (one per phase minimum).

## After this phase
This is the natural stopping point before picking one of plan.md §10's novel directions.
Bring the completed `04_final_replication_report.ipynb` and the limitations section to your
next meeting with Prof. Kasyap and your teammate before deciding which direction to pursue —
per plan.md's own closing recommendation, that choice should be made with the working
replication in hand, not before.
