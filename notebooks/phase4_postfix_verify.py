"""
Phase 4 Post-Fix Verification
==============================
After fixing the same-leg serialization bug, re-runs the 800 veh/hr
15-cycle conservation check and verifies:
1. Leg 0 queue clears every green cycle (matches Phase 3 behavior)
2. Total throughput is now consistent with Phase 3's single-leg result
3. All existing tests still pass (run separately via pytest)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

with open("configs/intersection_default.yaml") as f:
    config = yaml.safe_load(f)

from src.intersection.intersection import Intersection

RATE = 800
DURATION_S = 1950  # 15 cycles
cycle_len = config['signal']['cycle_length_s']
green_len = config['signal']['green_s']

# ─────────────────────────────────────────────────────────────────────────────
# Run 1: Pure car, check Leg 0 cycle-by-cycle queue clearing
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 65)
print("RUN 1: LEG 0 CYCLE CLEARING — Pure car, 800 veh/hr, 15 cycles")
print("=" * 65)

rng1 = np.random.default_rng(42)
inter1 = Intersection(config, RATE, DURATION_S, {"car": 1.0}, rng1)

leg0_snaps = []
for t in range(DURATION_S):
    inter1.step(t)
    leg0 = inter1.legs[0]
    stop_l = leg0.stop_line_position_cells
    q_before = sum(1 for v in leg0.vehicles if v.position_cells < stop_l)
    in_box   = sum(1 for v in leg0.vehicles if v.position_cells >= stop_l)
    phc = t % cycle_len
    leg0_snaps.append((t, q_before, in_box, len(leg0.vehicles), phc))

print(f"\nLeg 0 queue at end of GREEN (t%{cycle_len}=={green_len-1}):")
print(f"{'Cycle':>5} {'t':>5} {'Before stop':>12} {'In box':>7} {'Total':>7}  Result")
cleared_count = 0
for t, q, ib, tot, phc in leg0_snaps:
    if phc == green_len - 1:
        cyc = t // cycle_len
        ok = q == 0
        cleared_count += ok
        print(f"{cyc:>5} {t:>5} {q:>12} {ib:>7} {tot:>7}  {'✓ CLEARED' if ok else f'✗ {q} BACKLOG'}")

total_cycles = DURATION_S // cycle_len
print(f"\n{cleared_count}/{total_cycles} cycles fully cleared — {'✓ PASS: matches Phase 3 behavior' if cleared_count == total_cycles else '✗ STILL FAILING'}")

print(f"\nLeg 0 throughput (pure car):")
total_ins = inter1.vehicle_id_counter - 1
total_exits = inter1.natural_exits_count + inter1.forced_crossings_count
total_backlog = sum(len(leg.pending_arrivals) for leg in inter1.legs)
total_on_road = sum(len(leg.vehicles) for leg in inter1.legs)
print(f"  Inserted:        {total_ins}")
print(f"  Exited:          {total_exits}  ({total_exits/max(1,total_ins)*100:.1f}%)")
print(f"  Forced through:  {inter1.forced_crossings_count}")
print(f"  Natural exits:   {inter1.natural_exits_count}")
print(f"  Still on road:   {total_on_road}")
print(f"  Backlog:         {total_backlog}")
print(f"  Conserved:       {total_exits + total_on_road + total_backlog == total_ins + total_backlog}")

# ─────────────────────────────────────────────────────────────────────────────
# Run 2: Full mixed-mode, 800 veh/hr per leg, 15 cycles — the full Phase 4 check
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("RUN 2: FULL CONSERVATION CHECK — Mixed mode, 800 veh/hr, 15 cycles")
print("=" * 65)

mode_mix = {"two_wheeler": 0.546, "three_wheeler": 0.151, "car": 0.267, "bus": 0.036}
rng2 = np.random.default_rng(42)
inter2 = Intersection(config, RATE, DURATION_S, mode_mix, rng2)

for t in range(DURATION_S):
    inter2.step(t)

total_ins2 = inter2.vehicle_id_counter - 1
total_backlog2 = sum(len(leg.pending_arrivals) for leg in inter2.legs)
total_on_road2 = sum(len(leg.vehicles) for leg in inter2.legs)
total_gen2 = total_ins2 + total_backlog2
total_exits2 = inter2.natural_exits_count + inter2.forced_crossings_count

print(f"  Total generated: {total_gen2} (inserted={total_ins2}, backlog={total_backlog2})")
print(f"  Exited naturally:{inter2.natural_exits_count}")
print(f"  Forced through:  {inter2.forced_crossings_count}")
print(f"  Total exited:    {total_exits2}  ({total_exits2/max(1,total_ins2)*100:.1f}% of inserted)")
print(f"  Still on road:   {total_on_road2}")
print(f"  Conserved:       {total_exits2 + total_on_road2 + total_backlog2 == total_gen2}")
print(f"\n  Per-leg throughput (exits from {DURATION_S}s sim):")
print(f"    Expected (Phase 3 rate): ~{RATE * DURATION_S / 3600:.0f} veh processed per leg in {DURATION_S}s")
print(f"    Actual exits from all 4 legs: {total_exits2}")
print(f"    Avg per leg: {total_exits2/4:.1f}")

# ─────────────────────────────────────────────────────────────────────────────
# Run 3: Leg 0 cycle queue clearing — mixed mode  
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("RUN 3: LEG 0 QUEUE CLEARING — Mixed mode, 800 veh/hr, 15 cycles")
print("=" * 65)

mode_mix = {"two_wheeler": 0.546, "three_wheeler": 0.151, "car": 0.267, "bus": 0.036}
rng3 = np.random.default_rng(42)
inter3 = Intersection(config, RATE, DURATION_S, mode_mix, rng3)

leg0_mm = []
for t in range(DURATION_S):
    inter3.step(t)
    leg0 = inter3.legs[0]
    stop_l = leg0.stop_line_position_cells
    q_before = sum(1 for v in leg0.vehicles if v.position_cells < stop_l)
    in_box   = sum(1 for v in leg0.vehicles if v.position_cells >= stop_l)
    phc = t % cycle_len
    leg0_mm.append((t, q_before, in_box, len(leg0.vehicles), phc))

print(f"\nLeg 0 queue at end of GREEN (t%{cycle_len}=={green_len-1}): [mixed mode]")
print(f"{'Cycle':>5} {'t':>5} {'Before stop':>12} {'In box':>7} {'Total':>7}  Result")
cleared_mm = 0
for t, q, ib, tot, phc in leg0_mm:
    if phc == green_len - 1:
        cyc = t // cycle_len
        ok = q == 0
        cleared_mm += ok
        print(f"{cyc:>5} {t:>5} {q:>12} {ib:>7} {tot:>7}  {'✓ CLEARED' if ok else f'✗ {q} BACKLOG'}")

print(f"\n{cleared_mm}/{total_cycles} cycles fully cleared (mixed mode)")
print(f"{'✓ PASS' if cleared_mm == total_cycles else '⚠ PARTIAL — some cycles not clearing'}")

# ─────────────────────────────────────────────────────────────────────────────
# Run 4: Check all tests still pass
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("RUN PYTEST to verify no regressions")
print("=" * 65)
import subprocess
result = subprocess.run(
    [".venv/bin/python", "-m", "pytest", "-q", "--tb=short"],
    capture_output=True, text=True
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:2000])
