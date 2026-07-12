<div align="center">

# CA Seepage Simulator

### Cellular Automata Replication of Signalized Intersections with Non-Lane-Based Heterogeneous Traffic &amp; Seepage

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-active%20development-yellow)](#roadmap--phase-status)
[![Phase](https://img.shields.io/badge/phase-7%20of%2010%20complete-blue)](#roadmap--phase-status)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen?logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)
[![Paper](https://img.shields.io/badge/paper-DOI%2010.1177%2F03611981231211317-b31b1b)](https://doi.org/10.1177/03611981231211317)
[![Data](https://img.shields.io/badge/field%20data-Kanagaraj%20et%20al.%202015-orange)](#data-sources)

*A from-scratch replication and extension of Singh &amp; Ramachandra Rao (2023), built to study how* **seepage** *- small vehicles filtering and splitting through gaps in stopped traffic - reorders vehicles at signalized intersections.*

</div>

---

## Table of Contents

- [Overview](#overview)
- [Highlights](#highlights)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Results Snapshot](#results-snapshot)
- [Roadmap / Phase Status](#roadmap--phase-status)
- [Testing](#testing)
- [Data Sources](#data-sources)
- [Known Limitations](#known-limitations)
- [Citation](#citation)
- [Acknowledgments](#acknowledgments)
- [License](#license)

---

## Overview

This repository implements a cellular automata (CA) traffic simulator that replicates:

> Singh, M.K. &amp; Ramachandra Rao, K. (2023). *Simulation of Signalized Intersection with Non-Lane-Based Heterogeneous Traffic Conditions Using Cellular Automata.* Transportation Research Record. [DOI: 10.1177/03611981231211317](https://doi.org/10.1177/03611981231211317)

The simulator models a single isolated four-leg signalized intersection with:

- **4 vehicle modes** - two-wheeler, three-wheeler, car, bus - each with its own physical footprint and driving behavior
- **Non-lane-based movement** - vehicles occupy any lateral position within the road width, not fixed lanes
- **IZOI (Influence Zone of Intersection)** - a distance-based behavior switch where vehicles change from midblock to approach-to-signal driving rules
- **Seepage (Algorithm 3)** - the paper's central novel behavior: small vehicles (two-wheelers, three-wheelers) filter laterally and split diagonally through gaps between stopped larger vehicles during red, changing departure order relative to arrival order

The build follows a strict 10-phase roadmap (`docs/files/phase00_scaffolding.md` → `phase10_visualization_report.md`), where each phase's behavior is validated against real field data and paper-reported parameters before the next phase is built on top of it. See [`docs/files/plan.md`](docs/files/plan.md) for the full implementation plan.

---

## Highlights

- **Real field data, not synthetic.** Calibrated and tested against the [Kanagaraj et al. (2015)](#data-sources) Chennai heterogeneous-traffic trajectory dataset, with vehicle-type codes cross-checked against the dataset's own official documentation.
- **Paper-sourced parameters wherever available.** Grid geometry, vehicle dimensions, IZOI distances, signal timing, and turning proportions are pulled directly from the base paper's tables and equations rather than generic textbook defaults - see [`PHASE_REPORT.md`](PHASE_REPORT.md) for the full audit trail of which values are paper-sourced vs. literature placeholders.
- **Seepage-driven reordering, quantified.** A working instrumentation layer measures exactly how much seepage changes vehicle departure order relative to arrival order - the open research question this project set out to answer.
- **Rigorously stress-tested.** Every phase's acceptance criteria required an actual passing test suite, an attached and independently inspected plot, and a quantitative explanation for any surprising result - not just a plausible-sounding one. See [`PHASE_REPORT.md`](PHASE_REPORT.md) for the specific bugs this caught (vehicle-conservation violations, a double-movement bug in seepage, a window-boundary flow-counting bug, and others) before they could propagate into calibration or validation.
- **Honest, not just optimistic, results.** Where a result didn't hold up (e.g. calibrated parameters not reliably beating literature defaults on available field data), it's reported as such - see [Results Snapshot](#results-snapshot).

---

## Repository Structure

```
ca-seepage-sim/
  README.md                  <- you are here
  plan.md                    <- master implementation plan
  PHASE_REPORT.md            <- running log of what was built/found in each phase
  configs/
    intersection_default.yaml     <- paper/literature default parameters
    intersection_calibrated.yaml  <- field-calibrated parameters (Phase 7)
  data/
    raw/                     <- downloaded datasets (gitignored)
    processed/               <- cleaned trajectory + results CSVs
  src/
    core/                    <- Vehicle, Road/grid, gap calculations, NaSch motion rules
    intersection/            <- Signal, IZOI, seepage (Algorithm 3), routing, 4-leg assembly
    sim/                     <- vehicle generator, simulation loop, data collector
    metrics/                 <- density/flow (Eq 6-15), validation statistics (GEH, Theil's U, RMSE, RMSPE)
    calibration/              <- calibration objective (Eq 16) and NSGA-II + Nelder-Mead optimizer
    delay/                    <- simulated delay + highway capacity manual formulas
    viz/                      <- reusable plotting functions
  scripts/
    download_data.py         <- fetches and cleans the Kanagaraj field dataset
    run_calibration.py       <- runs the two-stage calibration optimizer
    run_validation.py        <- runs the statistical validation suite
    run_delay_comparison.py  <- runs simulated-vs-manual delay comparison
  tests/                     <- pytest suite, one file per module
  notebooks/                 <- exploratory and per-phase validation notebooks + figures/
  docs/files/                <- phase-by-phase implementation prompts (phase00 ... phase10)
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- ~1-2 GB free disk for field data and generated trajectory logs
- A few hours of wall-clock time if you intend to re-run calibration at full field-matched demand (see [Testing](#testing) for typical per-run costs)

### Installation

```bash
git clone <this-repo-url>
cd ca-seepage-sim

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Fetch the data

```bash
python scripts/download_data.py
```

Attempts to download the real Kanagaraj et al. (2015) Chennai trajectory dataset; falls back to a documented synthetic dataset with the same schema if the download fails, so the rest of the pipeline never blocks on network access.

---

## Usage

Run the pipeline stages in order:

```bash
# 1. Fetch and clean field data
python scripts/download_data.py

# 2. Calibrate driver-behavior parameters against field flow/density
python scripts/run_calibration.py

# 3. Validate the calibrated (and default) simulator against held-out field data
python scripts/run_validation.py

# 4. Compare simulated intersection delay against highway capacity manual formulas
python scripts/run_delay_comparison.py
```

Each script writes its outputs to `data/processed/` and figures to `notebooks/figures/`. The consolidated results notebook lives at `notebooks/04_final_replication_report.ipynb` once Phase 10 is complete.

---

## Results Snapshot

| Question | Finding |
|---|---|
| Does per-mode capacity order correctly? | Yes - two-wheeler > three-wheeler > car > bus, matching the base paper's Fig. 16 shape and its reported saturation flow range |
| How much does seepage change vehicle departure order? | ~6.7% of order-reversal events are directly seepage-attributed (36 of ~537 in a 6-cycle test run); the dominant source of reordering (~90%) is ordinary speed-differential overtaking during free-flow approach, independent of seepage |
| Does field-data calibration improve on the paper's literature parameters? | Not reliably - a 5-seed robustness check found calibrated parameters performed worse than literature defaults on 2 of 5 seeds, within the simulator's own stochastic noise floor. Most likely explanation: only midblock (not intersection-level) field data was available. See [Known Limitations](#known-limitations). |
| Is the core CA engine physically correct? | Yes, verified two independent ways (demand-driven and density-seeded simulation), both reproducing the expected triangular flow-density relationship |

Full detail and evidence for each of these is in `PHASE_REPORT.md`.

---

## Roadmap / Phase Status

| Phase | Description | Status |
|---|---|---|
| 0 | Scaffolding, config system, field-data pipeline | Complete |
| 1 | Core NaSch engine (single lane, single mode) | Complete |
| 2 | Multi-mode, non-lane-based 2D movement | Complete |
| 3 | Signal state machine + IZOI | Complete |
| 4 | Full 4-leg intersection + turning movements | Complete |
| 5 | Seepage (Algorithm 3) | Complete |
| 6 | Data collection & metrics layer | Complete |
| 7 | Calibration | Complete |
| 8 | Statistical validation | In progress |
| 9 | Delay estimation + manual benchmarking | Not started |
| 10 | Final visualization & report | Not started |

Detailed phase-by-phase specs live in [`docs/files/`](docs/files/); a running log of what was actually built, found, and fixed in each phase is in [`PHASE_REPORT.md`](PHASE_REPORT.md).

---

## Testing

```bash
pytest -q
```

Every module has dedicated unit tests, plus cross-cutting regression tests added as the project grew (vehicle-conservation accounting, cell-size consistency across modules, collision-safety under stress conditions, exact-match flow-counting). Full-suite runtime is on the order of tens of seconds; calibration/validation scripts that run full simulations at field-matched demand (~6,000+ veh/hr) are separately budgeted and take on the order of minutes to hours depending on scope - see the relevant script's `--help` or `PHASE_REPORT.md`'s Phase 7 wall-clock notes.

---

## Data Sources

- **Primary field dataset:** Kanagaraj, V., Asaithambi, G., Toledo, T., &amp; Lee, T.-C. (2015). Trajectory Data and Flow Characteristics of Mixed Traffic. *Transportation Research Record*, 2491, 1–11. Vehicle trajectory data from an urban midblock road section in Chennai, India - heterogeneous, non-lane-based traffic.
- **Base paper's own parameters:** grid geometry, vehicle dimensions, IZOI distances, and signal timing are drawn directly from Singh &amp; Ramachandra Rao (2023)'s tables and equations where reported (see `PHASE_REPORT.md` for the specific table/equation cited for each value).

---

## Known Limitations

- **Two-wheeler IZOI distance is a literature-derived placeholder** (100m), not a paper-reported value - the base paper's GPS deceleration data only covered cars, buses, and three-wheelers.
- **Calibration is based on midblock field data, not intersection-level field data.** The base paper's own Delhi/Mumbai intersection dataset is not publicly available. This limits calibration to car-following/lane-changing parameters; IZOI, turning proportions, and other intersection-specific parameters remain at literature values.
- **Junction conflict resolution uses a simplified, explicitly documented modeling assumption** (right-turn yields to opposing through traffic) where the base paper itself does not fully specify simultaneous-conflict resolution.
- **Turned vehicles are removed once they clear the junction box** rather than continuing as live traffic on their destination leg.
- **Calibration uses a single-objective GA + Nelder-Mead refinement** in place of the paper's MATLAB multi-objective `gamultiobj` + goal-attainment hybrid; distributional/behavioral replication was prioritized over exact parameter-value replication.

---

## Citation

If referencing this replication work, please cite the original paper:

```bibtex
@article{singh2023simulation,
  title   = {Simulation of Signalized Intersection with Non-Lane-Based
             Heterogeneous Traffic Conditions Using Cellular Automata},
  author  = {Singh, M. K. and Ramachandra Rao, K.},
  journal = {Transportation Research Record},
  year    = {2023},
  doi     = {10.1177/03611981231211317}
}
```

and the field dataset used for calibration/validation:

```bibtex
@article{kanagaraj2015trajectory,
  title   = {Trajectory Data and Flow Characteristics of Mixed Traffic},
  author  = {Kanagaraj, V. and Asaithambi, G. and Toledo, T. and Lee, T.-C.},
  journal = {Transportation Research Record},
  volume  = {2491},
  pages   = {1--11},
  year    = {2015}
}
```

---

## Acknowledgments

Developed as part of a summer research internship at IIT (BHU) Varanasi, under the supervision of Prof. Harsh Kasyap, with Evolve AI.

---

## License

MIT - see [`LICENSE`](LICENSE) for details. *(Update this section if a different license applies to your repository.)*