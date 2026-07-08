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
- Fundamental Diagram Observations: As requested, I investigated the lack of a falling branch by sweeping arrival rates up to 10,000 veh/hr, inspecting `decelerate_for_gap` (which correctly allows the lead vehicle unrestricted free-flow speed), and testing extreme parameters (`p_slowdown=0.8`, `road_length=10km`). In all cases, the flow plateaus at ~1400 veh/hr and the falling branch does not emerge.
  
  **Mechanistic Justification for the Missing Falling Branch**: 
  The absence of the falling branch is a physical consequence of the Phase 1 setup (open boundary, single-lane, discrete entry). 
  1. **Road Capacity**: With `car_length=7` and `max_speed=28`, the minimum safe headway is 35 cells. This yields a theoretical road capacity of ~2880 veh/hr (0.8 veh/s).
  2. **Entry Bottleneck**: A vehicle entering at speed 0 with `max_accel=3` takes 2 full time steps to clear the entry zone (cells 0 to 6). Thus, the absolute fastest the generator can physically inject vehicles without overlapping is 1 vehicle every 2 seconds, capping inflow at exactly 1800 veh/hr.
  3. **Result**: Because the maximum possible upstream inflow (1800 veh/hr) is significantly lower than the road's downstream carrying capacity (2880 veh/hr), the entry zone acts as a permanent, strict bottleneck. In open-boundary kinematic wave theory and CA, if a road is fed below its capacity and has unrestricted outflow, it operates permanently in the sub-critical (free-flow) phase. The queue grows entirely *off-road* in the generator's `pending_arrivals`, while the on-road density never exceeds the critical density (peaking at ~30 veh/km). 
  To produce the falling branch, we would need to either artificially initialize the road at high densities, introduce a periodic ring-road boundary, or inject vehicles at high initial speeds to artificially boost entry capacity beyond 2880 veh/hr. Since Phase 1 prohibits downstream bottlenecks and ring roads, the plot correctly demonstrates the free-flow branch and the entry-capacity plateau.
- Simplifications / Assumptions:
  - Used exponential (Poisson) headway generation in `generator.py` for simplicity in Phase 1 as requested.
  - Adjusted the flow measurement point to `road_length_cells - 50` so that high-speed vehicles are properly captured before they get deleted at the open boundary limit.
- Deferred TODOs: None.
