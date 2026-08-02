"""
stage8_smoke_and_regression.py — Run real-world map import smoke tests,
generate position plots, and execute regression checks for Stage 8.
"""

import sys
import os
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Ensure backend src is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from src.engine.simulation import Simulation
from src.mapdata.geocode import geocode
from src.mapdata.overpass_client import fetch_roads
from src.mapdata.osm_to_network import osm_to_network

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stage8_test")

EVIDENCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../docs/evidence/stage8"))
os.makedirs(EVIDENCE_DIR, exist_ok=True)

def plot_network(net, title: str, filename: str):
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Plot roads as lines
    for road_id, road in net.roads.items():
        x1 = road.x0
        y1 = road.y0
        x2 = road.x0 + road.dx * road.length
        y2 = road.y0 + road.dy * road.length
        ax.plot([x1, x2], [y1, y2], color='#1f77b4', alpha=0.7, linewidth=1.5)

    # Plot junctions
    jx = [j.x for j in net.junctions.values()]
    jy = [j.y for j in net.junctions.values()]
    ax.scatter(jx, jy, color='#d62728', s=20, zorder=3, label='Junctions')

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel("X (meters)", fontsize=11)
    ax.set_ylabel("Y (meters)", fontsize=11)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_aspect('equal', adjustable='datalim')
    ax.legend(loc='upper right')

    filepath = os.path.join(EVIDENCE_DIR, filename)
    plt.tight_layout()
    plt.savefig(filepath, dpi=200)
    plt.close()
    print(f"Saved plot to {filepath}")

def run_smoke_test(place_name: str, plot_filename: str):
    print(f"\n==================================================")
    print(f"Running Real-Data Smoke Test for: {place_name}")
    print(f"==================================================")
    
    sim = Simulation(seed=42)
    res = sim.import_region(place_name)
    
    if not res["ok"]:
        print(f"FAILED to import {place_name}: {res.get('error')}")
        return None, res

    print(f"Successfully imported {place_name}:")
    print(f"  - Road count: {res['roads']}")
    print(f"  - Junction count: {res['junctions']}")
    print(f"  - Total cells: {res['total_cells']}")

    # Step simulation for 500 steps
    max_occ_observed = 0
    vehicle_counts = []
    
    for step in range(500):
        sim.advance(1)
        total_veh = sum(len(r.vehicles) for r in sim.roads)
        vehicle_counts.append(total_veh)
        for r in sim.roads:
            occ = r.occupancy()
            m = occ.max() if len(occ) > 0 else 0
            if m > max_occ_observed:
                max_occ_observed = m

    print(f"  - Simulation ran 500 steps cleanly.")
    print(f"  - Vehicle count range over 500 steps: min {min(vehicle_counts)}, max {max(vehicle_counts)}, final {vehicle_counts[-1]}")
    print(f"  - Max cell occupancy observed across all 500 steps: {max_occ_observed} (Collision check: {'PASS' if max_occ_observed <= 1 else 'FAIL'})")

    # Plot
    plot_network(sim.network, f"Imported Network: {place_name}", plot_filename)
    
    return sim, res

def run_regression_comparison():
    print(f"\n==================================================")
    print(f"Running Flow-Density & Collision Regression Check")
    print(f"==================================================")

    # 1. Procedural Grid baseline (grid)
    sim_grid = Simulation(config="grid", seed=42)
    print(f"Baseline Network (grid): {len(sim_grid.roads)} roads, {len(sim_grid.network.junctions)} junctions, {sum(r.length for r in sim_grid.roads)} cells")
    
    # 2. Real imported network (IIT BHU) - import once
    sim_real = Simulation(seed=42)
    res = sim_real.import_region("IIT BHU Varanasi")
    assert res["ok"], "Failed to import IIT BHU for regression check"
    base_net = sim_real.network

    densities = [0.1, 0.3, 0.5, 0.7]

    print("\n--- Side-by-Side Flow & Collision Comparison ---")
    print(f"{'Target Rho':<12} | {'Grid Flow':<12} | {'Grid Max Occ':<12} | {'Real Flow':<12} | {'Real Max Occ':<12}")
    print("-" * 70)

    for rho in densities:
        # Test Grid
        sg = Simulation(config="grid", density=rho, seed=42)
        grid_max_occ = 0
        grid_flows = []
        for _ in range(300):
            sg.advance(1)
            grid_flows.append(sg.flow())
            for r in sg.roads:
                m = r.occupancy().max() if len(r.occupancy()) > 0 else 0
                if m > grid_max_occ: grid_max_occ = m
        avg_grid_flow = np.mean(grid_flows[100:])

        # Test Real (Populate density on imported structure)
        import copy
        sr = Simulation(seed=42)
        sr.network = copy.deepcopy(base_net)
        sr.network.populate_density(rho, 0.3, np.random.default_rng(42))
        real_max_occ = 0
        real_flows = []
        for _ in range(300):
            sr.advance(1)
            real_flows.append(sr.flow())
            for r in sr.roads:
                m = r.occupancy().max() if len(r.occupancy()) > 0 else 0
                if m > real_max_occ: real_max_occ = m
        avg_real_flow = np.mean(real_flows[100:])

        print(f"{rho:<12.2f} | {avg_grid_flow:<12.4f} | {grid_max_occ:<12d} | {avg_real_flow:<12.4f} | {real_max_occ:<12d}")

if __name__ == "__main__":
    run_smoke_test("IIT BHU Varanasi", "iit_bhu_network.png")
    run_smoke_test("IIEST Shibpur", "iiest_shibpur_network.png")
    run_regression_comparison()
