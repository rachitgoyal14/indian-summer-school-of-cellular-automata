import os
import numpy as np
import matplotlib.pyplot as plt
from src.core.cell import random_initial_state
from src.core.rule184 import step
from src.analytics.density import density_of, flow_at_step

def run_fd_check():
    # Parameters
    road_length = 1000
    warmup_steps = 500
    measure_steps = 500
    seed = 42
    
    # Initialize random number generator
    rng = np.random.default_rng(seed)
    
    # Density values from 0.05 to 0.95
    densities = np.arange(0.05, 1.0, 0.05)
    measured_densities = []
    measured_flows = []
    
    print("Running Rule 184 Flow-Density check...")
    print(f"Road length: {road_length} cells, Warmup: {warmup_steps} steps, Measurement: {measure_steps} steps")
    print("-" * 60)
    print(f"{'Target Density':<15}{'Actual Density':<15}{'Measured Flow':<15}{'Theoretical Flow':<15}")
    print("-" * 60)
    
    for target_rho in densities:
        # Initialize state with exact density
        state = random_initial_state(road_length, target_rho, rng)
        actual_rho = density_of(state)
        
        # Warm-up to reach steady-state
        for _ in range(warmup_steps):
            state = step(state, periodic=True)
            
        # Measurement window
        flows = []
        for _ in range(measure_steps):
            next_state = step(state, periodic=True)
            flows.append(flow_at_step(state, next_state))
            state = next_state
            
        avg_flow = float(np.mean(flows))
        theoretical_flow = min(actual_rho, 1.0 - actual_rho)
        
        measured_densities.append(actual_rho)
        measured_flows.append(avg_flow)
        
        print(f"{target_rho:<15.2f}{actual_rho:<15.4f}{avg_flow:<15.4f}{theoretical_flow:<15.4f}")
        
    # Theoretical curve
    theory_rho = np.linspace(0.0, 1.0, 500)
    theory_flow = np.minimum(theory_rho, 1.0 - theory_rho)
    
    # Plotting
    plt.figure(figsize=(9, 6), dpi=150)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    plt.plot(theory_rho, theory_flow, color='#1f77b4', linestyle='--', linewidth=2, label='Theoretical min(ρ, 1-ρ)')
    plt.scatter(measured_densities, measured_flows, color='#d62728', marker='o', s=60, zorder=5, label='Measured (Simulation)')
    
    plt.title('Rule 184: Fundamental Diagram (Flow vs. Density)', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Density (ρ) - Fraction of occupied cells', fontsize=11, labelpad=8)
    plt.ylabel('Flow (Q) - Average moving cars per cell per step', fontsize=11, labelpad=8)
    plt.xlim(-0.02, 1.02)
    plt.ylim(-0.02, 0.55)
    plt.xticks(np.arange(0.0, 1.1, 0.1))
    plt.yticks(np.arange(0.0, 0.6, 0.1))
    plt.legend(frameon=True, facecolor='white', framealpha=0.9, fontsize=11)
    plt.tight_layout()
    
    # Ensure docs directory exists
    os.makedirs('docs', exist_ok=True)
    plot_path = os.path.join('docs', 'phase1_flow_density.png')
    plt.savefig(plot_path, bbox_inches='tight')
    plt.close()
    
    print("-" * 60)
    print(f"Validation completed. Plot saved to: {plot_path}")

if __name__ == "__main__":
    run_fd_check()
