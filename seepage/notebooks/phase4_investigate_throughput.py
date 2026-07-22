"""
Phase 4 Throughput Investigation
=================================
Investigates the inconsistency between:
- Phase 3 (single leg, 800 veh/hr): clean sawtooth, queue fully clears every cycle
- Phase 4 (4-leg, 800 veh/hr per leg): massive backlog despite being sub-capacity

This script:
1. Measures Leg 0's per-cycle queue clearing in the 4-leg run
2. Checks if non-conflicting legs (Leg 0 + Leg 2: both green at same time) are
   spuriously blocking each other
3. Audits whether straight-through vehicles on concurrently-green legs have
   actually-overlapping paths in the junction box geometry
4. Identifies the specific bottleneck in the conflict resolution logic
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Load config
# ─────────────────────────────────────────────────────────────────────────────
with open("configs/intersection_default.yaml") as f:
    config = yaml.safe_load(f)

RATE = 800  # veh/hr per leg
DURATION_S = 1950  # 15 cycles of 130s
RNG = np.random.default_rng(42)

# ─────────────────────────────────────────────────────────────────────────────
# PART 1: Geometric Path Conflict Audit
# Manually compute which leg pairs have overlapping full-path-cells when going
# straight, using the same get_full_path_cells() logic.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("PART 1: GEOMETRIC PATH CONFLICT AUDIT (straight-through only)")
print("=" * 70)

from src.intersection.intersection import Intersection

rng_p1 = np.random.default_rng(42)
intersection_p1 = Intersection(config, RATE, DURATION_S, {"car": 1.0}, rng_p1)

W = intersection_p1.legs[0].road_width_cells
box_size = intersection_p1.box_size
print(f"W (road width cells): {W}")
print(f"Box size: {box_size}x{box_size}")
print()

# For a width-3 car at lat_pos=0 going straight:
car_width = 3
car_length = 7
lat_pos = 0  # leftmost lane

paths = {}
for leg_id in range(4):
    path = intersection_p1.get_full_path_cells(leg_id, lat_pos, 'straight', car_length, car_width)
    paths[leg_id] = path
    print(f"Leg {leg_id} straight path: {len(path)} cells, x range {min(c[0] for c in path)}-{max(c[0] for c in path)}, y range {min(c[1] for c in path)}-{max(c[1] for c in path)}")

print()
print("Path overlaps between leg pairs (straight-through):")
for i in range(4):
    for j in range(i+1, 4):
        overlap = paths[i].intersection(paths[j])
        # Which signal phase are these legs on?
        # Legs 0 & 2 → phase offset 0 (same green phase)
        # Legs 1 & 3 → phase offset 65 (same green phase)
        # Legs 0&1, 0&3, 1&2, 2&3 → opposing phases (cannot be simultaneously green)
        phase_i = "A" if i in [0, 2] else "B"
        phase_j = "A" if j in [0, 2] else "B"
        simultaneous = (phase_i == phase_j)
        conflict_marker = ""
        if overlap and simultaneous:
            conflict_marker = " ← ⚠️  SIMULTANEOUS GREEN + OVERLAPPING PATH = SPURIOUS BLOCK"
        elif overlap and not simultaneous:
            conflict_marker = " ← real conflict (opposing phases, expected)"
        elif not overlap and simultaneous:
            conflict_marker = " ← OK: same phase, no overlap"
        else:
            conflict_marker = " ← OK: opposing phase + no overlap"
        print(f"  Leg {i}(Phase {phase_i}) vs Leg {j}(Phase {phase_j}): {len(overlap)} overlapping cells{conflict_marker}")

# ─────────────────────────────────────────────────────────────────────────────
# PART 2: Run 4-leg sim but instrument Leg 0 per-cycle queue clearing
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("PART 2: LEG 0 CYCLE-BY-CYCLE QUEUE CLEARING IN 4-LEG SIM")
print("=" * 70)

from src.intersection.intersection import Intersection

rng_p2 = np.random.default_rng(42)
intersection_p2 = Intersection(config, RATE, DURATION_S, {"car": 1.0}, rng_p2)

cycle_len = config['signal']['cycle_length_s']
green_len = config['signal']['green_s']

# Track per-cycle queue at end of green phase for Leg 0
leg0_queue_at_end_of_green = []
leg0_queue_at_end_of_red = []
leg0_exits_per_cycle = []
leg0_entry_t_tracker = {}  # vehicle_id -> step of first appearance on Leg 0

prev_leg0_vehicles = set()
cycle_exits = 0

# Run step by step, recording Leg 0 state
for t in range(DURATION_S):
    records = intersection_p2.step(t)
    
    leg0 = intersection_p2.legs[0]
    phase_in_cycle = t % cycle_len
    
    # Count queue = vehicles before stop line on Leg 0
    stop_line = leg0.stop_line_position_cells
    leg0_queue = sum(1 for v in leg0.vehicles if v.position_cells < stop_line)
    
    # End of green phase for Leg 0 (phase A: green is 0..green_len-1)
    if phase_in_cycle == green_len - 1:
        cycle_num = t // cycle_len
        leg0_queue_at_end_of_green.append((cycle_num, t, leg0_queue, len(leg0.vehicles)))

    # End of red phase (= just before next green)
    if phase_in_cycle == cycle_len - 1:
        cycle_num = t // cycle_len
        leg0_queue_at_end_of_red.append((cycle_num, t, leg0_queue, len(leg0.vehicles)))

print(f"\nLeg 0 signal: Phase A (offset=0), green=t%{cycle_len} in [0,{green_len-1}]")
print(f"\nQueue count (vehicles BEFORE stop line) at end of GREEN phase:")
print(f"{'Cycle':>6} {'t':>6} {'Queue before stop':>18} {'Total on road':>14}")
for cycle_num, t, q_before, total in leg0_queue_at_end_of_green[:16]:
    cleared = "✓ CLEARED" if q_before == 0 else f"✗ BACKLOG={q_before}"
    print(f"{cycle_num:>6} {t:>6} {q_before:>18} {total:>14}  {cleared}")

print(f"\nQueue count (vehicles BEFORE stop line) at end of RED phase (max queue):")
print(f"{'Cycle':>6} {'t':>6} {'Queue before stop':>18} {'Total on road':>14}")
for cycle_num, t, q_before, total in leg0_queue_at_end_of_red[:16]:
    print(f"{cycle_num:>6} {t:>6} {q_before:>18} {total:>14}")

# ─────────────────────────────────────────────────────────────────────────────
# PART 3: Check whether 'future_reservations' is the serializer
# Run a 2-step sim with only Leg 0 and Leg 2 (both should be green simultaneously)
# and see if they block each other in the junction box
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("PART 3: DO Leg 0 AND Leg 2 BLOCK EACH OTHER (SAME-PHASE LEGS)?")
print("=" * 70)

# Count how many times the gridlock-prevention check fires for Leg 0
# when blocked vehicle is from Leg 2 (same green phase)
# We'll monkey-patch the blocked check to log it

from src.intersection.intersection import Intersection as IntersectionOrig

block_events = []  # (t, blocker_leg, blocked_leg)

class InstrumentedIntersection(IntersectionOrig):
    def step(self, t):
        # Re-implement conflict check with logging
        records = []
        mode_params = self.config['mode_params']
        modes = list(self.config['mode_params'].keys())
        
        # 1. Generate new arrivals
        for leg in self.legs:
            probs = [self.config.get('mode_mix', {}).get(m, 1.0/len(modes)) for m in modes]
            total = sum(probs)
            probs = [p/total for p in probs]
            while leg.next_arrival_idx < len(leg.arrivals) and leg.arrivals[leg.next_arrival_idx] <= t:
                chosen_mode = self.rng.choice(modes, p=probs)
                leg.pending_arrivals.append(chosen_mode)
                leg.next_arrival_idx += 1
            inserted_this_step = 0
            while leg.pending_arrivals and inserted_this_step < 10:
                from src.core.vehicle import Vehicle
                from src.intersection.routing import choose_turn
                mode = leg.pending_arrivals[0]
                params = mode_params[mode]
                v_length = params['length_cells']
                v_width = params['width_cells']
                best_lat = -1
                best_gap = -1
                for lat in range(leg.road_width_cells - v_width + 1):
                    entry_clear = True
                    min_back = leg.road_length_cells
                    for v in leg.vehicles:
                        v_left = v.lateral_position_cells
                        v_right = v.lateral_position_cells + v.width_cells - 1
                        c_left = lat
                        c_right = lat + v_width - 1
                        if c_left <= v_right and v_left <= c_right:
                            v_back = v.position_cells - v.length_cells + 1
                            if v_back <= v_length - 1:
                                entry_clear = False
                                break
                            if v_back < min_back:
                                min_back = v_back
                    if entry_clear:
                        gap = min_back - v_length
                        if gap > best_gap:
                            best_gap = gap
                            best_lat = lat
                if best_lat >= 0:
                    initial_speed = min(params['max_speed_cells_per_step'], max(0, best_gap))
                    new_vehicle = Vehicle(
                        id=self.vehicle_id_counter, mode=mode,
                        length_cells=v_length, width_cells=v_width,
                        max_speed_cells_per_step=params['max_speed_cells_per_step'],
                        max_accel_cells_per_step2=params['max_accel_cells_per_step2'],
                        position_cells=v_length - 1, lateral_position_cells=best_lat,
                        speed_cells_per_step=initial_speed
                    )
                    leg.vehicles.append(new_vehicle)
                    leg.turn_directions[new_vehicle.id] = choose_turn(mode, leg.turn_proportions, self.rng)
                    self.vehicle_id_counter += 1
                    leg.pending_arrivals.pop(0)
                    inserted_this_step += 1
                else:
                    break

        # 2. Build global occupancy
        junction_occupancy = {}
        for leg in self.legs:
            for v in leg.vehicles:
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past >= 0:
                    turn = leg.turn_directions[v.id]
                    cells = self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells)
                    for c in cells:
                        junction_occupancy[c] = (leg.leg_id, v.id, turn, pos_past)
        
        # 3. Accelerate & decelerate
        from src.core.motion import accelerate, decelerate_for_gap, update_positions
        izoi_config = self.config['izoi_distance_m']
        izoi_decel_rate = self.config['izoi_deceleration_rate']
        for leg in self.legs:
            accelerate(leg.vehicles)
            decelerate_for_gap(leg.vehicles)
        
        # INSTRUMENTED conflict resolution
        def turn_priority(turn_str):
            return 1 if turn_str in ["straight", "left"] else 0
        all_vehicles = []
        for leg in self.legs:
            for v in leg.vehicles:
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past >= -30 and pos_past < 2*self.box_size:
                    in_box = pos_past >= 0
                    dwell_s = (t - self.junction_entry_t.get(v.id, t)) if in_box else 0
                    row_status = 1 if (in_box and dwell_s > self.max_box_dwell_s) else 0
                    all_vehicles.append((leg, v, row_status))
        all_vehicles.sort(key=lambda item: (
            item[2],
            item[1].position_cells - item[0].stop_line_position_cells,
            turn_priority(item[0].turn_directions[item[1].id]),
            -item[1].id
        ), reverse=True)
        
        current_occupancy = {}
        future_reservations = {}
        for leg, v, _ in all_vehicles:
            pos_past = v.position_cells - leg.stop_line_position_cells
            if pos_past >= 0:
                turn = leg.turn_directions[v.id]
                for cx, cy in self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                    if 0 <= cx < self.box_size and 0 <= cy < self.box_size:
                        current_occupancy[(cx, cy)] = v.id
        
        for leg, v, row_status in all_vehicles:
            turn = leg.turn_directions[v.id]
            speed = int(v.speed_cells_per_step)
            my_progress = v.position_cells - leg.stop_line_position_cells
            
            if row_status == 1:
                if v.id not in self.forced_crossing_ids:
                    self.forced_crossing_ids.add(v.id)
                if v.speed_cells_per_step == 0:
                    v.speed_cells_per_step = 5
                speed = int(v.speed_cells_per_step)
                granted_right_of_way = True
            else:
                granted_right_of_way = False
            
            # INSTRUMENTED: log which leg is blocking which
            if my_progress < 0 and my_progress + speed >= 0 and not granted_right_of_way:
                my_path = self.get_full_path_cells(leg.leg_id, v.lateral_position_cells, turn, v.length_cells, v.width_cells)
                blocked = False
                for other_leg, other_v, other_row in all_vehicles:
                    if other_v.id != v.id:
                        other_progress = other_v.position_cells - other_leg.stop_line_position_cells
                        W = self.box_size // 2
                        other_turn = other_leg.turn_directions.get(other_v.id, 'straight')
                        other_exit = (W + other_v.length_cells) if other_turn != 'straight' else (2 * self.box_size)
                        if 0 <= other_progress < other_exit:
                            other_path = self.get_full_path_cells(other_leg.leg_id, other_v.lateral_position_cells, other_turn, other_v.length_cells, other_v.width_cells)
                            if my_path.intersection(other_path):
                                blocked = True
                                # LOG: who blocked whom
                                block_events.append({
                                    't': t,
                                    'blocked_leg': leg.leg_id,
                                    'blocked_vid': v.id,
                                    'blocked_turn': turn,
                                    'blocker_leg': other_leg.leg_id,
                                    'blocker_vid': other_v.id,
                                    'blocker_turn': other_turn,
                                })
                                break
                if blocked:
                    speed = max(0, int(-my_progress - 1))
                    v.speed_cells_per_step = speed
            
            for step_ahead in range(1, speed + 1):
                pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
                if pos_past >= 0:
                    future_cells = self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells)
                    conflict = False
                    for cx, cy in future_cells:
                        if 0 <= cx < self.box_size and 0 <= cy < self.box_size:
                            c = (cx, cy)
                            if c in current_occupancy and current_occupancy[c] != v.id:
                                conflict = True
                                break
                            if c in future_reservations:
                                other_vid, other_progress, other_row_status = future_reservations[c]
                                if other_vid != v.id:
                                    if not granted_right_of_way or (other_row_status == 1 and other_progress >= my_progress):
                                        conflict = True
                                        break
                    if conflict:
                        v.speed_cells_per_step = step_ahead - 1
                        break
            
            my_progress = v.position_cells - leg.stop_line_position_cells
            for step_ahead in range(1, int(v.speed_cells_per_step) + 1):
                pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
                if pos_past >= 0:
                    for cx, cy in self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                        if 0 <= cx < self.box_size and 0 <= cy < self.box_size:
                            c = (cx, cy)
                            if c not in future_reservations or future_reservations[c][1] <= my_progress:
                                future_reservations[c] = (v.id, pos_past, row_status)
        
        # Signal + IZOI
        from src.intersection.izoi import is_in_izoi, izoi_behavior
        from src.core.gaps import lateral_gap
        from src.core.lane_change import decide_lateral_move
        for leg in self.legs:
            current_signal = leg.signal.state_at(t)
            skip_randomization = set()
            for v in leg.vehicles:
                izoi_dist_cells = int(izoi_config[v.mode] / leg.cell_length_m)
                v_front = v.position_cells
                gap_to_stop = leg.stop_line_position_cells - v_front - 1
                min_gap_izoi = v.speed_cells_per_step
                if v_front < leg.stop_line_position_cells and current_signal == "red":
                    actual_min_gap = min(min_gap_izoi, gap_to_stop)
                else:
                    actual_min_gap = min_gap_izoi
                if is_in_izoi(v, leg.stop_line_position_cells, izoi_dist_cells):
                    action = izoi_behavior(v, current_signal, izoi_decel_rate, actual_min_gap)
                    if action == "decelerate_izoi":
                        skip_randomization.add(v.id)
                else:
                    if current_signal == "red" and v_front < leg.stop_line_position_cells:
                        v.speed_cells_per_step = min(v.speed_cells_per_step, max(0, gap_to_stop))
            for v in leg.vehicles:
                if v.position_cells < leg.stop_line_position_cells:
                    params = mode_params[v.mode]
                    gaps = lateral_gap(v, leg.vehicles)
                    lat_move = decide_lateral_move(v, gaps, params['position_preference'], params['lane_change_prob'], leg.road_width_cells, self.rng)
                    v.lateral_position_cells += lat_move
            for v in leg.vehicles:
                if v.id not in skip_randomization:
                    p_slow = mode_params[v.mode]['p_slowdown']
                    if v.speed_cells_per_step > 0 and self.rng.random() < p_slow:
                        v.speed_cells_per_step -= 1
            leg.vehicles = update_positions(leg.vehicles, leg.road_length_cells + 2*self.box_size)
            W = self.box_size // 2
            surviving = []
            for v in leg.vehicles:
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past >= 0 and v.id not in self.junction_entry_t:
                    self.junction_entry_t[v.id] = t
                turn = leg.turn_directions.get(v.id, 'straight')
                exit_threshold = 2 * self.box_size if turn == 'straight' else W + v.length_cells
                if pos_past < exit_threshold:
                    surviving.append(v)
                else:
                    if v.id in self.forced_crossing_ids:
                        self.forced_crossings_count += 1
                    else:
                        self.natural_exits_count += 1
            leg.vehicles = surviving
            for v in leg.vehicles:
                records.append({
                    "time_s": t,
                    "vehicle_id": v.id,
                    "mode": v.mode,
                    "leg_origin": leg.leg_id,
                    "turn": leg.turn_directions[v.id],
                    "position_cells": v.position_cells,
                    "lateral_position_cells": v.lateral_position_cells,
                    "speed_cells_per_step": v.speed_cells_per_step,
                    "signal": current_signal
                })
        return records


rng_p3 = np.random.default_rng(42)
instr_intersection = InstrumentedIntersection(config, RATE, DURATION_S, {"car": 1.0}, rng_p3)
for t in range(DURATION_S):
    instr_intersection.step(t)

df_blocks = pd.DataFrame(block_events)
print(f"\nTotal block events logged: {len(df_blocks)}")
if len(df_blocks) > 0:
    print("\nBlock events by (blocked_leg, blocker_leg) pair:")
    pair_counts = df_blocks.groupby(['blocked_leg', 'blocker_leg', 'blocked_turn', 'blocker_turn']).size().reset_index(name='count')
    pair_counts = pair_counts.sort_values('count', ascending=False)
    for _, row in pair_counts.iterrows():
        # Determine if these legs are concurrently green
        def phase(leg_id):
            return "A" if leg_id in [0, 2] else "B"
        same_phase = (phase(int(row['blocked_leg'])) == phase(int(row['blocker_leg'])))
        marker = "⚠️  SAME-PHASE SPURIOUS BLOCK" if same_phase else "real conflict (opposing phase)"
        print(f"  Leg {int(row['blocked_leg'])} ({row['blocked_turn']}) blocked by Leg {int(row['blocker_leg'])} ({row['blocker_turn']}): {int(row['count'])} times  [{marker}]")

# ─────────────────────────────────────────────────────────────────────────────
# PART 4: Check future_reservations serialization between Leg 0 & Leg 2
# Even without the gridlock-prevention check, future_reservations may serialize
# same-phase legs if their paths share even 1 cell
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("PART 4: DO Leg 0 AND Leg 2 PATHS SHARE CELLS? (would cause future_reservations serialization)")
print("=" * 70)

# Full path for Leg 0 straight
p0 = intersection_p1.get_full_path_cells(0, 0, 'straight', car_length, car_width)
p2 = intersection_p1.get_full_path_cells(2, 0, 'straight', car_length, car_width)
p1 = intersection_p1.get_full_path_cells(1, 0, 'straight', car_length, car_width)
p3 = intersection_p1.get_full_path_cells(3, 0, 'straight', car_length, car_width)

print(f"Leg 0 path: {len(p0)} cells")
print(f"Leg 2 path: {len(p2)} cells")
print(f"Leg 1 path: {len(p1)} cells")
print(f"Leg 3 path: {len(p3)} cells")

print(f"\nLeg 0 ∩ Leg 2 (same green phase): {len(p0.intersection(p2))} cells overlap")
print(f"Leg 1 ∩ Leg 3 (same green phase): {len(p1.intersection(p3))} cells overlap")
print(f"Leg 0 ∩ Leg 3 (same green phase): {len(p0.intersection(p3))} cells overlap")
print(f"Leg 2 ∩ Leg 1 (same green phase): {len(p2.intersection(p1))} cells overlap")

print(f"\nLeg 0 ∩ Leg 1 (opposing phases): {len(p0.intersection(p1))} cells overlap")
print(f"Leg 0 ∩ Leg 3 (opposing phases... wait Leg 0 is Phase A, Leg 3 is Phase B)")

# Recheck phase assignments
print()
print("Phase assignment reminder:")
print("  Legs 0 & 2: Phase A (offset 0, green when t%130 in [0,29])")
print("  Legs 1 & 3: Phase B (offset 65, green when t%130 in [65,94])")
print()
for i in range(4):
    for j in range(i+1, 4):
        pi = "A" if i in [0, 2] else "B"
        pj = "A" if j in [0, 2] else "B"
        same = pi == pj
        path_i = intersection_p1.get_full_path_cells(i, 0, 'straight', car_length, car_width)
        path_j = intersection_p1.get_full_path_cells(j, 0, 'straight', car_length, car_width)
        overlap_size = len(path_i.intersection(path_j))
        print(f"Leg {i}(Ph {pi}) vs Leg {j}(Ph {pj}): {'SAME' if same else 'OPPOSING'} phase, {overlap_size} overlapping cells in junction box")

# ─────────────────────────────────────────────────────────────────────────────
# PART 5: Conservation check after full 15-cycle run (same as Phase 4 report)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("PART 5: FINAL 15-CYCLE CONSERVATION CHECK (current code)")
print("=" * 70)

rng_p5 = np.random.default_rng(42)
mode_mix = {"two_wheeler": 0.546, "three_wheeler": 0.151, "car": 0.267, "bus": 0.036}
inter_p5 = Intersection(config, RATE, DURATION_S, mode_mix, rng_p5)

all_records = []
for t in range(DURATION_S):
    records_t = inter_p5.step(t)
    all_records.extend(records_t)

total_inserted = inter_p5.vehicle_id_counter - 1
total_backlog = sum(len(leg.pending_arrivals) for leg in inter_p5.legs)
total_on_road = sum(len(leg.vehicles) for leg in inter_p5.legs)
total_exited = inter_p5.natural_exits_count
total_forced = inter_p5.forced_crossings_count
total_generated = total_inserted + total_backlog

print(f"Total generated: {total_generated} (inserted={total_inserted}, backlog={total_backlog})")
print(f"Exited naturally: {total_exited}")
print(f"Forced through: {total_forced}")
print(f"Still on road: {total_on_road}")
total_accounted = total_exited + total_forced + total_on_road + total_backlog
print(f"Conservation: {total_accounted} == {total_generated}? {total_accounted == total_generated}")
print(f"Exit rate: {total_exited + total_forced}/{total_inserted} = {(total_exited + total_forced)/max(1,total_inserted)*100:.1f}%")
print(f"Backlog rate: {total_backlog}/{total_generated} = {total_backlog/max(1,total_generated)*100:.1f}%")
