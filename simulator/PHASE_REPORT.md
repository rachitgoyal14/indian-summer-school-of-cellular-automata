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

### Detailed Sanity & Convergence Checks
To verify the exact matching of theoretical and simulated values, we performed deeper diagnostic runs:

1. **Standard Deviation over the Measurement Window:**
   We computed the standard deviation of the flow across the 500 measurement steps for three representative densities. The step-to-step flow standard deviation is exactly **zero**:
   - **$\rho = 0.05$**: Mean Flow = $0.0500$, Std Dev = $0.000000$
   - **$\rho = 0.50$**: Mean Flow = $0.5000$, Std Dev = $0.000000$
   - **$\rho = 0.95$**: Mean Flow = $0.0500$, Std Dev = $0.000000$

2. **Seed Independence / Sensitivity to Initial Conditions:**
   We ran the simulation with density $\rho = 0.30$ across 5 different random seeds, measuring flow and standard deviation for each:
   - **Seed 1**: Actual Density = $0.3000$, Mean Flow = $0.3000$, Std Dev = $0.000000$
   - **Seed 10**: Actual Density = $0.3000$, Mean Flow = $0.3000$, Std Dev = $0.000000$
   - **Seed 42**: Actual Density = $0.3000$, Mean Flow = $0.3000$, Std Dev = $0.000000$
   - **Seed 100**: Actual Density = $0.3000$, Mean Flow = $0.3000$, Std Dev = $0.000000$
   - **Seed 999**: Actual Density = $0.3000$, Mean Flow = $0.3000$, Std Dev = $0.000000$

3. **Theoretical Rationale for Zero Variance:**
   Rule 184 is a completely deterministic, discrete-time cellular automaton.
   - For **low density ($\rho \le 0.5$)**: Over the 500-step warm-up window (which is larger than the road length $L=1000$ divided by the velocity, i.e., $O(L)$ transient time), any random initial placement of cars will dissolve its local jams and settle into a steady state where all cars are separated by at least one empty cell. At this point, every single car moves forward by 1 cell on every single time step. Thus, $v_i = 1$ for all cars, and the flow is exactly $Q = \rho$ at every single time step, yielding a standard deviation of zero. Since all initial conditions settle into this same class of attractors, the steady-state flow is identical (to bit precision) regardless of the seed.
   - For **high density ($\rho > 0.5$)**: By particle-hole symmetry, the empty cells (holes) act as particles moving backwards with speed 1. At steady state, all holes are separated by at least one car. This means on every step, a car moves into every empty cell. The number of moving cars on every single step is exactly equal to the number of holes, $L(1 - \rho)$, giving a constant flow of $Q = 1 - \rho$, with zero step-to-step variance and absolute seed independence.

4. **Actual Density Matching Target Density Exactly:**
   The "actual density" column matches the "target density" to 4 decimal places because `random_initial_state` computes:
   $$\text{num\_cars} = \text{round}(L \times \rho)$$
   For our test runs, $L = 1000$ and target densities $\rho \in \{0.05, 0.10, \dots, 0.95\}$. Since $L \times \rho$ is exactly an integer (e.g. $1000 \times 0.05 = 50$), rounding does not shift the car count. Thus, the actual density $\rho_{\text{actual}} = \text{num\_cars} / L$ is mathematically and bitwise identical to the target density.

### Flow-Density Plot
The measured data points lie **exactly** on the theoretical min(ρ, 1-ρ) triangle:

![Rule 184 Fundamental Diagram](docs/phase1_flow_density.png)

This perfect agreement confirms the correctness of the core Rule 184 traffic engine. We are ready to proceed to Phase 2.
