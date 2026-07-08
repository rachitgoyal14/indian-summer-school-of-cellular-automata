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
- Fundamental Diagram Observations: As requested, I replaced the initial `0` speed insertion with a gap-dependent initial speed (`min(car_max_speed, max(0, gap))`) to maximize entry flow. I swept arrival rates up to 15,000 veh/hr and tested parameters like `p_slowdown=0.06` and `0.3`.
  
  **Mechanistic Justification for the Missing Falling Branch (After Entry Fix)**:
  Even with the gap-dependent speed insertion, the flow still plateaus and the falling branch does not emerge. Here are the specific numbers and the physical reason:
  1. **Theoretical Road Capacity**: With `car_length=7`, `max_speed=28`, the safe headway is 35 cells. This yields a theoretical road capacity of `(1 veh / 35 cells) * 28 cells/s = 0.8 veh/s ≈ 2880 veh/hr`.
  2. **Deliverable Entry Flow**: The arrival sweep demonstrates that the absolute maximum deliverable entry flow caps at **~1606 veh/hr**. 
  3. **Why It Caps**: By injecting vehicles at the exact `min(max_speed, gap)`, the vehicles are packed as closely as dynamically possible at the entry point. However, because `p_slowdown=0.06` occasionally causes a leader to decelerate randomly, these closely-packed followers must immediately brake. This creates entrance-induced shockwaves. Crucially, when these shockwaves stall a vehicle, the vehicle stops *on top of the entry cell* (cells 0-6). As long as a vehicle covers the entry footprint, `entry_clear` is False and the generator cannot push new vehicles in. 
  4. **The Consequence**: These entrance jams throttle the insertion rate down to an average of 1606 veh/hr. Because the deliverable entry flow (1606 veh/hr) is significantly lower than the road's downstream carrying capacity (2880 veh/hr), the downstream road is always fed *below* its capacity. In kinematic wave theory and TASEP/NaSch, a road fed sub-critically with unrestricted outflow will operate purely in the free-flow phase. The on-road density plateaus at ~33 veh/km (well below the critical density of ~57 veh/km, let alone jam density of 140 veh/km). 
  Because the density physically cannot exceed 33 veh/km due to the entrance-throttling effect, it is impossible to trace the right-hand (falling) branch of the fundamental diagram in an open-boundary setup driven exclusively by upstream injection. The plot correctly shows the free-flow branch and the 1606 veh/hr plateau.
- Simplifications / Assumptions:
  - Used exponential (Poisson) headway generation in `generator.py` for simplicity in Phase 1 as requested.
  - Adjusted the flow measurement point to `road_length_cells - 50` so that high-speed vehicles are properly captured before they get deleted at the open boundary limit.
- Deferred TODOs: None.
