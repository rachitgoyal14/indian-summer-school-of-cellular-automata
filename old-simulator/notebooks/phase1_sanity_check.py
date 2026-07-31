import numpy as np
from src.core.cell import random_initial_state
from src.core.rule184 import step
from src.analytics.density import density_of, flow_at_step

def run_sanity_check():
    road_length = 1000
    warmup_steps = 500
    measure_steps = 500
    
    print("--- 1. Checking Standard Deviation of Flow Over Time ---")
    check_densities = [0.05, 0.50, 0.95]
    rng = np.random.default_rng(42)
    
    for rho in check_densities:
        state = random_initial_state(road_length, rho, rng)
        # Warmup
        for _ in range(warmup_steps):
            state = step(state, periodic=True)
        # Measure
        flows = []
        for _ in range(measure_steps):
            next_state = step(state, periodic=True)
            flows.append(flow_at_step(state, next_state))
            state = next_state
        
        mean_flow = np.mean(flows)
        std_flow = np.std(flows)
        print(f"Density {rho:.2f}: Mean Flow = {mean_flow:.4f}, Std Dev = {std_flow:.6f}")
        
    print("\n--- 2. Running Density 0.3 with 5 Different Seeds ---")
    seeds = [1, 10, 42, 100, 999]
    for seed in seeds:
        rng_seed = np.random.default_rng(seed)
        state = random_initial_state(road_length, 0.30, rng_seed)
        actual_rho = density_of(state)
        # Warmup
        for _ in range(warmup_steps):
            state = step(state, periodic=True)
        # Measure
        flows = []
        for _ in range(measure_steps):
            next_state = step(state, periodic=True)
            flows.append(flow_at_step(state, next_state))
            state = next_state
        mean_flow = np.mean(flows)
        std_flow = np.std(flows)
        print(f"Seed {seed:<5}: Actual Density = {actual_rho:.4f}, Mean Flow = {mean_flow:.4f}, Std Dev = {std_flow:.6f}")

if __name__ == "__main__":
    run_sanity_check()
