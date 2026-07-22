# PHASE 0 — Environment & Scaffolding

## Before you start
Read `00_START_HERE.md` in this same folder and follow ALL ground rules in it for this
and every subsequent phase. Read `plan.md` (repo root, once created) sections 1, 2, 3
(Phase 0 only), 5, 7, and 8 before writing anything.

## Goal of this phase
Stand up the repo skeleton, a config system, logging, a test harness, and load ONE
real (or synthetic-fallback) dataset into a pandas DataFrame with a first exploratory
plot. **No simulation logic yet.** This phase produces zero vehicle-movement code.

## Exact steps

1. Create the repo:
   ```
   ca-seepage-sim/
     README.md
     plan.md                <- copy the plan.md content you were given into here verbatim
     PHASE_REPORT.md         <- create with just a title line "# Phase Reports"
     configs/
       intersection_default.yaml
     data/
       raw/
       processed/
     src/
       core/
       intersection/
       sim/
       metrics/
       calibration/
       delay/
         manuals/
       viz/
       __init__.py files in every package dir
     scripts/
       download_data.py
     tests/
     notebooks/
       01_explore_raw_data.ipynb
     requirements.txt
     .gitignore              <- ignore data/raw/, .venv/, __pycache__, *.pyc, .ipynb_checkpoints
   ```
   Every `src/**` subfolder needs an `__init__.py` so it's a proper Python package.

2. Initialize git (`git init`) and make the first commit after step 1's skeleton exists.

3. Set up `.venv`, activate it, install: `numpy pandas scipy matplotlib pyyaml pytest openpyxl requests`.
   Pin versions in `requirements.txt` (use `pip freeze > requirements.txt`).

4. **Config system** (`src/core/config.py`):
   - A `load_config(path: str) -> dict` function that reads a YAML file and returns a plain dict
     (do not over-engineer with a custom class yet — a dict is fine for now).
   - `configs/intersection_default.yaml` must contain (values are placeholders you choose
     sensibly now — they WILL be overwritten by calibration in Phase 7):
     ```yaml
     grid:
       cell_length_m: 0.5
       cell_width_m: 0.7
       lane_width_m: 3.5
     legs: 4
     simulation:
       time_step_s: 1
       duration_s: 3600
       random_seed: 42
     modes: [two_wheeler, three_wheeler, car, bus]
     ```
   - Write a unit test `tests/test_config.py` asserting the YAML loads and has the `modes` key
     with exactly 4 entries.

5. **Logging** (`src/core/logging_setup.py`): a `get_logger(name: str)` helper using Python's
   standard `logging` module, INFO level to console, DEBUG level to a rotating file under
   `logs/` (create that dir, add it to `.gitignore`).

6. **Data download script** (`scripts/download_data.py`):
   - Attempt to download, in this priority order, stopping at the first success:
     1. Kanagaraj et al. (2015) Chennai trajectory data:
        `https://toledo.net.technion.ac.il/files/2014/10/ChennaiTrajectoryData2.45-3.00PM.xlsx`
        and the 3:00–3:15 PM part at the equivalent `...3.00-3.15PM.xlsx` URL.
     2. If that fails (404, timeout, connection error — catch and log, do not crash), print a
        clear WARNING and fall back to generating **synthetic trajectory data**.
   - Synthetic fallback generator: simulate ~200 vehicles over a 900-second window on a
     200m single-direction road segment, 4 modes, using simple Gaussian-noise-perturbed
     constant-speed trajectories per mode (rough speed ranges: two_wheeler 8-14 m/s,
     three_wheeler 6-11 m/s, car 7-13 m/s, bus 5-9 m/s). Output columns must be:
     `vehicle_id, mode, time_s, x_m, y_m, speed_mps`. Save to
     `data/processed/trajectories_synthetic.csv`.
   - Real data, once downloaded, should be cleaned into the SAME column schema and saved to
     `data/processed/trajectories_kanagaraj.csv` (the Kanagaraj file's actual columns won't
     match exactly — inspect the downloaded xlsx first with pandas, then write an explicit
     column-rename/derive step; do not guess column names blindly, print `df.columns.tolist()`
     and `df.head()` first and adapt the mapping code to what you actually see).
   - The script must never raise unhandled exceptions — wrap the whole download attempt in
     try/except and always end with a valid file in `data/processed/`.

7. **Exploration notebook** (`notebooks/01_explore_raw_data.ipynb`):
   - Load whichever processed CSV exists (prefer the real one if present, else synthetic).
   - Plot: (a) all vehicle x-position vs time trajectories on one chart, colored by mode,
     (b) a histogram of speeds per mode, (c) a headway distribution (time gap between
     consecutive vehicles at a fixed x cross-section, computed by interpolation).
   - Save the three plots as PNGs to `notebooks/figures/` in addition to displaying inline.

8. **Tests** (`tests/`):
   - `test_config.py` (from step 4)
   - `test_download_data.py`: asserts that after running the download function, a file
     matching `data/processed/trajectories_*.csv` exists and has the 6 required columns
     and at least 50 rows. Mock/skip the actual network call in the test (test the fallback
     path directly, or test against a tiny fixture, so CI doesn't depend on internet access).

## Acceptance criteria (do not report this phase done until all are true)
- [ ] `pytest -q` passes with 0 failures.
- [ ] `python scripts/download_data.py` runs to completion without raising, and leaves a valid
      CSV in `data/processed/` matching the schema above.
- [ ] The notebook runs top-to-bottom without errors and produces 3 PNGs in `notebooks/figures/`.
- [ ] `PHASE_REPORT.md` has a `## Phase 0 — Scaffolding` section per the Ground Rules format,
      explicitly stating whether real Kanagaraj data or synthetic fallback data was used.
- [ ] Git history has at least 2 commits (skeleton, then working scaffolding).

## Explicitly out of scope for this phase
Do not implement any vehicle motion, grid occupancy, or NaSch rules yet — that's Phase 1.
This phase is infrastructure only.
