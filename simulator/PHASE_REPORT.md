# Phase Report: General CA Traffic Simulator (Rule 184)

## Phase 1 — Core Rule 184 Engine (No Graphics)

### Implementation Overview
In Phase 1, we implemented the core mathematical foundation of the Rule 184 traffic simulator inside the `simulator` directory.

The implementation consists of the following key modules:
- **[cell.py](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/simulator/src/core/cell.py)**: Manages 1D road representation via a NumPy array of 0s (empty) and 1s (occupied). Includes `random_initial_state` to initialize a road of length $L$ with an exact number of cars corresponding to target density $\rho$, rounded to the nearest integer.
- **[rule184.py](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/simulator/src/core/rule184.py)**: Implements the `step` function for synchronous updates. Supports both periodic boundaries (ring road) and open boundaries (vehicles exit at the end, and no new vehicles enter at the beginning).
- **[density.py](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/simulator/src/analytics/density.py)**: Calculates actual density $\rho$ and flow $Q$ (defined as the average fraction of cells where a car successfully advances to the next cell per step).

### Verification of Synchronous Updates
As highlighted in `plan.md`, the single most critical detail in Rule 184 is ensuring a **synchronous (simultaneous) update**. If the cells are updated sequentially (e.g., left-to-right or right-to-left), cars can move multiple times in a single step, which breaks the exact traffic flow physics.

In our implementation of `rule184.py`, the update is fully vectorized and synchronous:
```python
prev_neighbor = np.roll(state, 1)
next_neighbor = np.roll(state, -1)
new_state = np.where(state == 1, next_neighbor, prev_neighbor).astype(np.int8)
```
Using `np.where`, the state at $t+1$ is computed strictly from a read-only snapshot of the state at time $t$. 

We wrote unit tests in **[test_rule184.py](file:///Users/rachitgoyal/Desktop/cellular-automata-work/ca-seepage-sim/simulator/tests/test_rule184.py)** that verify this behavior. Specifically, the test `test_rule184_simultaneous_vs_sequential` asserts that `[1, 1, 0, 0]` under periodic boundary conditions evaluates to `[1, 0, 1, 0]`. If it were updated sequentially from right to left, the state would incorrectly evaluate to `[0, 1, 1, 0]` (as the car at index 1 would move to 2, and then the car at index 0 would immediately move to the freed-up index 1 in the same step).

Running `pytest` shows that all tests pass:
```
tests/test_rule184.py::test_random_initial_state PASSED
tests/test_rule184.py::test_rule184_periodic_basic PASSED
tests/test_rule184.py::test_rule184_simultaneous_vs_sequential PASSED
tests/test_rule184.py::test_rule184_open_basic PASSED
tests/test_rule184.py::test_density_and_flow PASSED
```

### Flow-Density Fundamental Diagram Check
Rule 184 under periodic boundaries is exactly solvable and yields the following theoretical relation between density $\rho$ and flow $Q$:
$$Q(\rho) = \min(\rho, 1 - \rho)$$

We ran a validation check across 19 density values (evenly spaced from $0.05$ to $0.95$) on a 1000-cell periodic road. For each density, the simulation ran for 500 warm-up steps to reach a steady state, followed by 500 steps of measurement.

The results are tabulated below:

| Target Density | Actual Density | Measured Flow | Theoretical Flow | Error |
|:---|:---|:---|:---|:---|
| 0.05 | 0.0500 | 0.0500 | 0.0500 | 0.0000 |
| 0.10 | 0.1000 | 0.1000 | 0.1000 | 0.0000 |
| 0.15 | 0.1500 | 0.1500 | 0.1500 | 0.0000 |
| 0.20 | 0.2000 | 0.2000 | 0.2000 | 0.0000 |
| 0.25 | 0.2500 | 0.2500 | 0.2500 | 0.0000 |
| 0.30 | 0.3000 | 0.3000 | 0.3000 | 0.0000 |
| 0.35 | 0.3500 | 0.3500 | 0.3500 | 0.0000 |
| 0.40 | 0.4000 | 0.4000 | 0.4000 | 0.0000 |
| 0.45 | 0.4500 | 0.4500 | 0.4500 | 0.0000 |
| 0.50 | 0.5000 | 0.5000 | 0.5000 | 0.0000 |
| 0.55 | 0.5500 | 0.4500 | 0.4500 | 0.0000 |
| 0.60 | 0.6000 | 0.4000 | 0.4000 | 0.0000 |
| 0.65 | 0.6500 | 0.3500 | 0.3500 | 0.0000 |
| 0.70 | 0.7000 | 0.3000 | 0.3000 | 0.0000 |
| 0.75 | 0.7500 | 0.2500 | 0.2500 | 0.0000 |
| 0.80 | 0.8000 | 0.2000 | 0.2000 | 0.0000 |
| 0.85 | 0.8500 | 0.1500 | 0.1500 | 0.0000 |
| 0.90 | 0.9000 | 0.1000 | 0.1000 | 0.0000 |
| 0.95 | 0.9500 | 0.0500 | 0.0500 | 0.0000 |

### Flow-Density Plot
The measured data points lie **exactly** on the theoretical min(ρ, 1-ρ) triangle:

![Rule 184 Fundamental Diagram](docs/phase1_flow_density.png)

This perfect agreement confirms the correctness of the core Rule 184 traffic engine. We are ready to proceed to Phase 2.
