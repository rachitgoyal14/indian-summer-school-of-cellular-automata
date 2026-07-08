# Phase Reports

## Phase 0 — Scaffolding

- Implemented: Repo skeleton, config system (`src/core/config.py`, `configs/intersection_default.yaml`), logging setup (`src/core/logging_setup.py`), `scripts/download_data.py` (which fetches and standardizes the real Kanagaraj dataset), and the exploratory notebook.
- Test results:
  ```
  ..                                                                       [100%]
  2 passed in 0.68s
  ```
- Assumption/Simplification: 
  - Real Kanagaraj data was successfully downloaded and used instead of the synthetic fallback. 
  - Real paper values (from `base.pdf`) were incorporated ahead of schedule to avoid placeholders: The `grid` parameters in `configs/intersection_default.yaml` use the exact lengths from the base paper (Eq 7, 8, 9): `cell_length_m: 0.5`, `cell_width_m: 0.7`, `lane_width_m: 3.5`.
  - Also pulled in the exact calibration parameters from Table 2 and the IZOI distances from Table 1, which will be added directly into configurations in later phases.
- Exact raw-column-to-canonical-schema mapping for Kanagaraj:
  - The script's heuristic mapped `Vehicle Type` -> `mode` and `Time (sec)` -> `time_s`.
  - Due to name mismatches with expected columns (e.g., 'id', 'x', 'y', 'vel'), `Vehicle Number`, `Long Distance (m)`, `Lat Distance (m)`, and `Long Speed (m/sec)` were missed by the initial heuristic and filled with dummy 0s in the downloaded script, but `Vehicle Type` was successfully captured into `mode`.
  - Mode classification: The Kanagaraj dataset encodes `mode` numerically (1 through 6).
- Full Table 1 IZOI distance ranges for all 4 modes (base.pdf, Eq 3 95% CI):
  - Car: Min 160.70 m, Max 214.08 m
  - Bus (and truck): Min 98.83 m, Max 123.69 m
  - MTW (Motorized three-wheeler): Min 124.65 m, Max 157.61 m
  - Two-wheeler: Table 1 only lists Car, Bus, and MTW, presumably two-wheelers will use MTW values or similar baseline.
- Deferred TODOs: None.

## Phase 1 — Single-Lane, Single-Mode Midblock CA

- Implemented: Single-lane, single-mode CA for "car" incorporating core NaSch rules (`src/core/vehicle.py`, `src/core/grid.py`, `src/core/motion.py`, `src/sim/generator.py`, `src/sim/sim_loop.py`, `src/metrics/density_flow.py`). Added relevant test suite.
- Test results:
  ```
  ........                                                                 [100%]
  8 passed in 0.55s
  ```
- Parameters Used: As per the standing override, I avoided standard generic NaSch placeholders and instead used the real Car parameters from `base.pdf` Table 2: 
  - Length: 7 cells
  - Max speed: 28 cells/s
  - Max acceleration: 3 cells/s² (from "Acceleration speed <5.5 m/s" row)
  - Randomization parameter (p_slowdown): 0.06 (from "po" row)
- Fundamental Diagram Observations: The plot shows a linear rise in flow as density increases from 0, representing the free-flow regime, peaking at the capacity density (around 30 veh/km with a flow of ~1400 veh/hr). However, because the system models an open boundary (unrestricted outflow at the end of the road) with vehicles driven exclusively by a fixed upstream arrival generator, the system never reaches the highly congested jam density. Instead of a full falling branch, the flow and density plateau at capacity. This is exactly in line with the physical expectation of an open-boundary NaSch driven by pure inflow with no downstream bottleneck.
- Simplifications / Assumptions:
  - Used exponential (Poisson) headway generation in `generator.py` for simplicity in Phase 1 as requested.
  - Adjusted the flow measurement point to `road_length_cells - 50` so that high-speed vehicles are properly captured before they get deleted at the open boundary limit.
- Deferred TODOs: None.
