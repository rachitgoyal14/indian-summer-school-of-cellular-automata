"""
Phase 4 Post-Fix Quick Verification (5 cycles = 650s)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml
import subprocess

with open("configs/intersection_default.yaml") as f:
    config = yaml.safe_load(f)

from src.intersection.intersection import Intersection

RATE = 800
DURATION_5 = 650   # 5 cycles
DURATION_15 = 1950  # 15 cycles (used for conservation check only)
cycle_len = config['signal']['cycle_length_s']
green_len = config['signal']['green_s']

# ─────────────────────────────────────────────────────────────────────────────
# Run 1: Pure car, 5 cycles — Leg 0 queue clearing
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 65)
print("RUN 1: LEG 0 QUEUE CLEARING — Pure car, 800 veh/hr, 5 cycles")
print("=" * 65)

rng1 = np.random.default_rng(42)
inter1 = Intersection(config, RATE, DURATION_5, {"car": 1.0}, rng1)

leg0_snaps = []
for t in range(DURATION_5):
    inter1.step(t)
    leg0 = inter1.legs[0]
    stop_l = leg0.stop_line_position_cells
    q_before = sum(1 for v in leg0.vehicles if v.position_cells < stop_l)
    in_box   = sum(1 for v in leg0.vehicles if v.position_cells >= stop_l)
    phc = t % cycle_len
    leg0_snaps.append((t, q_before, in_box, len(leg0.vehicles), phc))

print(f"\nLeg 0 at end of GREEN (t%{cycle_len}=={green_len-1}):")
print(f"{'Cycle':>5} {'t':>5} {'Before stop':>12} {'In box':>7} {'Total':>7}  Result")
cleared_count = 0
total_green_checks = 0
for t, q, ib, tot, phc in leg0_snaps:
    if phc == green_len - 1:
        cyc = t // cycle_len
        ok = q == 0
        cleared_count += ok
        total_green_checks += 1
        print(f"{cyc:>5} {t:>5} {q:>12} {ib:>7} {tot:>7}  {'✓ CLEARED' if ok else f'✗ {q} BACKLOG'}")

print(f"\n{cleared_count}/{total_green_checks} cycles fully cleared (pure car)")
if cleared_count == total_green_checks:
    print("✓ PASS: Leg 0 queue clears every cycle — matches Phase 3!")
else:
    print("✗ STILL FAILING")

print(f"\nThroughput (pure car, {DURATION_5}s):")
ins1 = inter1.vehicle_id_counter - 1
exits1 = inter1.natural_exits_count + inter1.forced_crossings_count
backlog1 = sum(len(leg.pending_arrivals) for leg in inter1.legs)
on_road1 = sum(len(leg.vehicles) for leg in inter1.legs)
print(f"  Inserted: {ins1}  Exits: {exits1} ({exits1/max(1,ins1)*100:.1f}%)  On road: {on_road1}  Backlog: {backlog1}")
print(f"  Conservation: {exits1 + on_road1 + backlog1 == ins1 + backlog1}")

# ─────────────────────────────────────────────────────────────────────────────
# Run 2: Mixed mode, 5 cycles — Leg 0 queue clearing
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("RUN 2: LEG 0 QUEUE CLEARING — Mixed mode, 800 veh/hr, 5 cycles")
print("=" * 65)

mode_mix = {"two_wheeler": 0.546, "three_wheeler": 0.151, "car": 0.267, "bus": 0.036}
rng2 = np.random.default_rng(42)
inter2 = Intersection(config, RATE, DURATION_5, mode_mix, rng2)

leg0_mm = []
for t in range(DURATION_5):
    inter2.step(t)
    leg0 = inter2.legs[0]
    stop_l = leg0.stop_line_position_cells
    q_before = sum(1 for v in leg0.vehicles if v.position_cells < stop_l)
    in_box   = sum(1 for v in leg0.vehicles if v.position_cells >= stop_l)
    phc = t % cycle_len
    leg0_mm.append((t, q_before, in_box, len(leg0.vehicles), phc))

print(f"\nLeg 0 at end of GREEN (t%{cycle_len}=={green_len-1}): [mixed mode]")
print(f"{'Cycle':>5} {'t':>5} {'Before stop':>12} {'In box':>7} {'Total':>7}  Result")
cleared_mm = 0
for t, q, ib, tot, phc in leg0_mm:
    if phc == green_len - 1:
        cyc = t // cycle_len
        ok = q == 0
        cleared_mm += 1 if ok else 0
        print(f"{cyc:>5} {t:>5} {q:>12} {ib:>7} {tot:>7}  {'✓ CLEARED' if ok else f'✗ {q} BACKLOG'}")

print(f"\n{cleared_mm}/{total_green_checks} cycles fully cleared (mixed mode)")

print(f"\nThroughput (mixed mode, {DURATION_5}s):")
ins2 = inter2.vehicle_id_counter - 1
exits2 = inter2.natural_exits_count + inter2.forced_crossings_count
backlog2 = sum(len(leg.pending_arrivals) for leg in inter2.legs)
on_road2 = sum(len(leg.vehicles) for leg in inter2.legs)
print(f"  Inserted: {ins2}  Exits: {exits2} ({exits2/max(1,ins2)*100:.1f}%)  On road: {on_road2}  Backlog: {backlog2}")
print(f"  Conservation: {exits2 + on_road2 + backlog2 == ins2 + backlog2}")

# ─────────────────────────────────────────────────────────────────────────────
# Run pytest
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("PYTEST — regression tests")
print("=" * 65)
result = subprocess.run(
    [".venv/bin/python", "-m", "pytest", "-q", "--tb=short", "-x"],
    capture_output=True, text=True, cwd="."
)
print(result.stdout[-3000:])
if result.returncode != 0 and result.stderr:
    print("STDERR:", result.stderr[:1000])
