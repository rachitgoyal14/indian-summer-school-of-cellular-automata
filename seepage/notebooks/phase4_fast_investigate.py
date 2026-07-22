"""
Phase 4 Throughput Investigation — FAST VERSION
================================================
Focuses on the key questions only, minimal simulation time.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml
import pandas as pd

with open("configs/intersection_default.yaml") as f:
    config = yaml.safe_load(f)

RATE = 800
RNG_SEED = 42

# ─────────────────────────────────────────────────────────────────────────────
# PART 1: Geometric path conflict audit (no simulation needed)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("PART 1: GEOMETRIC PATH AUDIT — which leg pairs overlap?")
print("=" * 70)

from src.intersection.intersection import Intersection

dummy_rng = np.random.default_rng(42)
dummy = Intersection(config, 100, 200, {"car": 1.0}, dummy_rng)

W = dummy.legs[0].road_width_cells
box_size = dummy.box_size
print(f"W={W}, box={box_size}x{box_size}")

car_w = 3
car_l = 7

phase_name = {0: "A", 1: "B", 2: "A", 3: "B"}

print("\nLeg layout (straight-through):")
print("  Leg 0 (N→S, Phase A): x in [W+lat..W+lat+w-1], y from 2W-1 down to 0")
print("  Leg 1 (E→W, Phase B): y in [W+lat..W+lat+w-1], x from 2W-1 down to 0")
print("  Leg 2 (S→N, Phase A): x in [lat..lat+w-1],     y from 0 up to 2W-1")
print("  Leg 3 (W→E, Phase B): y in [lat..lat+w-1],     x from 0 up to 2W-1")
print()

# Check all lat positions for any overlap between same-phase legs
print("Checking SAME-PHASE pairs (Leg0+Leg2=A, Leg1+Leg3=B) for ALL lat positions:")
for lat in range(W - car_w + 1):
    p0 = dummy.get_full_path_cells(0, lat, 'straight', car_l, car_w)
    p2 = dummy.get_full_path_cells(2, lat, 'straight', car_l, car_w)
    p1 = dummy.get_full_path_cells(1, lat, 'straight', car_l, car_w)
    p3 = dummy.get_full_path_cells(3, lat, 'straight', car_l, car_w)
    ov02 = len(p0 & p2)
    ov13 = len(p1 & p3)
    print(f"  lat={lat}: Leg0∩Leg2={ov02} cells, Leg1∩Leg3={ov13} cells")

print()
print("Cross-phase pairs (should conflict, that's expected):")
for lat in [0]:
    p = {}
    for i in range(4):
        p[i] = dummy.get_full_path_cells(i, lat, 'straight', car_l, car_w)
    for (i, j) in [(0,1),(0,3),(2,1),(2,3)]:
        ov = len(p[i] & p[j])
        print(f"  Leg{i}(Ph {phase_name[i]}) ∩ Leg{j}(Ph {phase_name[j]}) at lat=0: {ov} cells")

# ─────────────────────────────────────────────────────────────────────────────
# PART 2: Block event counting — 3 cycles only, pure-car, instrumented
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("PART 2: BLOCK EVENTS — 3 cycles (390s), pure car mode")
print("=" * 70)

block_events = []
future_res_conflicts = []  # track future_reservations serializations

from src.core.motion import accelerate, decelerate_for_gap, update_positions
from src.intersection.izoi import is_in_izoi, izoi_behavior
from src.core.gaps import lateral_gap
from src.core.lane_change import decide_lateral_move
from src.intersection.routing import choose_turn
from src.core.vehicle import Vehicle

mode_mix_car = {"car": 1.0}
rng2 = np.random.default_rng(42)
inter2 = Intersection(config, RATE, 390, mode_mix_car, rng2)

cycle_len = config['signal']['cycle_length_s']
green_len = config['signal']['green_s']
izoi_config = config['izoi_distance_m']
izoi_decel_rate = config['izoi_deceleration_rate']
mode_params = config['mode_params']
modes = list(mode_params.keys())

phase_name = {0: "A", 1: "B", 2: "A", 3: "B"}

def get_sig_phase(leg_id, t):
    return inter2.legs[leg_id].signal.state_at(t)

def is_same_phase_pair(leg_a, leg_b):
    """True if both legs are on the same signal phase (both A or both B)"""
    return phase_name[leg_a] == phase_name[leg_b]

for t in range(390):
    # Generate arrivals
    for leg in inter2.legs:
        probs_raw = [config.get('mode_mix', {}).get(m, 1.0/len(modes)) for m in modes]
        total = sum(probs_raw)
        probs = [p/total for p in probs_raw]
        while leg.next_arrival_idx < len(leg.arrivals) and leg.arrivals[leg.next_arrival_idx] <= t:
            chosen_mode = rng2.choice(modes, p=probs)
            leg.pending_arrivals.append(chosen_mode)
            leg.next_arrival_idx += 1
        ins = 0
        while leg.pending_arrivals and ins < 10:
            mode = leg.pending_arrivals[0]
            params = mode_params[mode]
            v_l = params['length_cells']; v_w = params['width_cells']
            best_lat = -1; best_gap = -1
            for lat in range(leg.road_width_cells - v_w + 1):
                entry_clear = True; min_back = leg.road_length_cells
                for v in leg.vehicles:
                    vl = v.lateral_position_cells; vr = vl + v.width_cells - 1
                    cl = lat; cr = lat + v_w - 1
                    if cl <= vr and vl <= cr:
                        vb = v.position_cells - v.length_cells + 1
                        if vb <= v_l - 1: entry_clear = False; break
                        if vb < min_back: min_back = vb
                if entry_clear:
                    gap = min_back - v_l
                    if gap > best_gap: best_gap = gap; best_lat = lat
            if best_lat >= 0:
                spd = min(params['max_speed_cells_per_step'], max(0, best_gap))
                nv = Vehicle(id=inter2.vehicle_id_counter, mode=mode,
                             length_cells=v_l, width_cells=v_w,
                             max_speed_cells_per_step=params['max_speed_cells_per_step'],
                             max_accel_cells_per_step2=params['max_accel_cells_per_step2'],
                             position_cells=v_l-1, lateral_position_cells=best_lat,
                             speed_cells_per_step=spd)
                leg.vehicles.append(nv)
                leg.turn_directions[nv.id] = choose_turn(mode, leg.turn_proportions, rng2)
                inter2.vehicle_id_counter += 1
                leg.pending_arrivals.pop(0); ins += 1
            else:
                break

    # Accelerate & gap decelerate
    for leg in inter2.legs:
        accelerate(leg.vehicles)
        decelerate_for_gap(leg.vehicles)

    # Conflict resolution with instrumentation
    def turn_priority(s): return 1 if s in ["straight","left"] else 0
    all_vehicles = []
    for leg in inter2.legs:
        for v in leg.vehicles:
            pos_past = v.position_cells - leg.stop_line_position_cells
            if pos_past >= -30 and pos_past < 2*inter2.box_size:
                in_box = pos_past >= 0
                dwell = (t - inter2.junction_entry_t.get(v.id, t)) if in_box else 0
                row = 1 if (in_box and dwell > inter2.max_box_dwell_s) else 0
                all_vehicles.append((leg, v, row))
    all_vehicles.sort(key=lambda x: (x[2], x[1].position_cells - x[0].stop_line_position_cells,
                                      turn_priority(x[0].turn_directions[x[1].id]), -x[1].id), reverse=True)

    current_occupancy = {}
    future_reservations = {}
    for leg, v, _ in all_vehicles:
        pos_past = v.position_cells - leg.stop_line_position_cells
        if pos_past >= 0:
            turn = leg.turn_directions[v.id]
            for cx, cy in inter2.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                if 0 <= cx < inter2.box_size and 0 <= cy < inter2.box_size:
                    current_occupancy[(cx,cy)] = v.id

    for leg, v, row_status in all_vehicles:
        turn = leg.turn_directions[v.id]
        speed = int(v.speed_cells_per_step)
        my_progress = v.position_cells - leg.stop_line_position_cells

        if row_status == 1:
            if v.id not in inter2.forced_crossing_ids:
                inter2.forced_crossing_ids.add(v.id)
            if v.speed_cells_per_step == 0: v.speed_cells_per_step = 5
            speed = int(v.speed_cells_per_step)
            gow = True
        else:
            gow = False

        # GRIDLOCK CHECK — log who blocks whom
        if my_progress < 0 and my_progress + speed >= 0 and not gow:
            my_path = inter2.get_full_path_cells(leg.leg_id, v.lateral_position_cells, turn, v.length_cells, v.width_cells)
            blocked = False
            for other_leg, other_v, other_row in all_vehicles:
                if other_v.id != v.id:
                    op = other_v.position_cells - other_leg.stop_line_position_cells
                    WT = inter2.box_size // 2
                    ot = other_leg.turn_directions.get(other_v.id, 'straight')
                    oe = (WT + other_v.length_cells) if ot != 'straight' else (2*inter2.box_size)
                    if 0 <= op < oe:
                        other_path = inter2.get_full_path_cells(other_leg.leg_id, other_v.lateral_position_cells, ot, other_v.length_cells, other_v.width_cells)
                        if my_path & other_path:
                            same_ph = is_same_phase_pair(leg.leg_id, other_leg.leg_id)
                            my_sig = get_sig_phase(leg.leg_id, t)
                            other_sig = get_sig_phase(other_leg.leg_id, t)
                            block_events.append({
                                't': t,
                                'blocked_leg': leg.leg_id,
                                'blocker_leg': other_leg.leg_id,
                                'blocked_turn': turn,
                                'blocker_turn': ot,
                                'same_phase': same_ph,
                                'my_signal': my_sig,
                                'other_signal': other_sig,
                            })
                            blocked = True
                            break
            if blocked:
                speed = max(0, int(-my_progress - 1))
                v.speed_cells_per_step = speed

        # Future path check — log future_reservations conflicts  
        for step_ahead in range(1, speed + 1):
            pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
            if pos_past >= 0:
                future_cells = inter2.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells)
                conflict = False
                for cx, cy in future_cells:
                    if 0 <= cx < inter2.box_size and 0 <= cy < inter2.box_size:
                        c = (cx, cy)
                        if c in current_occupancy and current_occupancy[c] != v.id:
                            conflict = True
                            break
                        if c in future_reservations:
                            other_vid, other_prog, other_row_s = future_reservations[c]
                            if other_vid != v.id:
                                if not gow or (other_row_s == 1 and other_prog >= my_progress):
                                    # Find which leg this other vehicle belongs to
                                    other_leg_id = None
                                    for ol, ov, _ in all_vehicles:
                                        if ov.id == other_vid:
                                            other_leg_id = ol.leg_id
                                            break
                                    if other_leg_id is not None:
                                        same_ph = is_same_phase_pair(leg.leg_id, other_leg_id)
                                        future_res_conflicts.append({
                                            't': t,
                                            'my_leg': leg.leg_id,
                                            'other_leg': other_leg_id,
                                            'same_phase': same_ph,
                                            'my_signal': get_sig_phase(leg.leg_id, t),
                                            'other_signal': get_sig_phase(other_leg_id, t),
                                        })
                                    conflict = True
                                    break
                if conflict:
                    v.speed_cells_per_step = step_ahead - 1
                    break

        my_progress = v.position_cells - leg.stop_line_position_cells
        for step_ahead in range(1, int(v.speed_cells_per_step) + 1):
            pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
            if pos_past >= 0:
                for cx, cy in inter2.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                    if 0 <= cx < inter2.box_size and 0 <= cy < inter2.box_size:
                        c = (cx, cy)
                        if c not in future_reservations or future_reservations[c][1] <= my_progress:
                            future_reservations[c] = (v.id, pos_past, row_status)

    # Signal + IZOI + move
    for leg in inter2.legs:
        cur_sig = leg.signal.state_at(t)
        skip_rand = set()
        for v in leg.vehicles:
            izoi_d = int(izoi_config[v.mode] / leg.cell_length_m)
            v_front = v.position_cells
            gap_to_stop = leg.stop_line_position_cells - v_front - 1
            mg = v.speed_cells_per_step
            if v_front < leg.stop_line_position_cells and cur_sig == "red":
                amg = min(mg, gap_to_stop)
            else:
                amg = mg
            if is_in_izoi(v, leg.stop_line_position_cells, izoi_d):
                action = izoi_behavior(v, cur_sig, izoi_decel_rate, amg)
                if action == "decelerate_izoi": skip_rand.add(v.id)
            else:
                if cur_sig == "red" and v_front < leg.stop_line_position_cells:
                    v.speed_cells_per_step = min(v.speed_cells_per_step, max(0, gap_to_stop))
        for v in leg.vehicles:
            if v.position_cells < leg.stop_line_position_cells:
                params = mode_params[v.mode]
                gaps = lateral_gap(v, leg.vehicles)
                lm = decide_lateral_move(v, gaps, params['position_preference'], params['lane_change_prob'], leg.road_width_cells, rng2)
                v.lateral_position_cells += lm
        for v in leg.vehicles:
            if v.id not in skip_rand:
                p_slow = mode_params[v.mode]['p_slowdown']
                if v.speed_cells_per_step > 0 and rng2.random() < p_slow:
                    v.speed_cells_per_step -= 1
        leg.vehicles = update_positions(leg.vehicles, leg.road_length_cells + 2*inter2.box_size)
        WW = inter2.box_size // 2
        surviving = []
        for v in leg.vehicles:
            pos_past = v.position_cells - leg.stop_line_position_cells
            if pos_past >= 0 and v.id not in inter2.junction_entry_t:
                inter2.junction_entry_t[v.id] = t
            tv = leg.turn_directions.get(v.id, 'straight')
            et = 2*inter2.box_size if tv == 'straight' else WW + v.length_cells
            if pos_past < et:
                surviving.append(v)
            else:
                if v.id in inter2.forced_crossing_ids: inter2.forced_crossings_count += 1
                else: inter2.natural_exits_count += 1
        leg.vehicles = surviving

print(f"\nGridlock-prevention block events in 390s:")
df_b = pd.DataFrame(block_events)
if len(df_b) > 0:
    print(f"  Total: {len(df_b)}")
    grp = df_b.groupby(['blocked_leg','blocker_leg','same_phase','my_signal','other_signal']).size().reset_index(name='count').sort_values('count', ascending=False)
    for _, r in grp.iterrows():
        ph_note = "⚠️  SAME-PHASE" if r['same_phase'] else "✓ opposing phase"
        print(f"  Leg{int(r['blocked_leg'])} (sig={r['my_signal']}) blocked by Leg{int(r['blocker_leg'])} (sig={r['other_signal']}) — {ph_note} — count={int(r['count'])}")
else:
    print("  NONE! Gridlock-prevention check never fires.")

print(f"\nFuture-reservations serialization conflicts in 390s:")
df_fr = pd.DataFrame(future_res_conflicts)
if len(df_fr) > 0:
    print(f"  Total: {len(df_fr)}")
    grp2 = df_fr.groupby(['my_leg','other_leg','same_phase','my_signal','other_signal']).size().reset_index(name='count').sort_values('count', ascending=False)
    for _, r in grp2.head(20).iterrows():
        ph_note = "⚠️  SAME-PHASE SPURIOUS SERIALIZATION" if r['same_phase'] else "✓ legitimate (opposing phase)"
        print(f"  Leg{int(r['my_leg'])} (sig={r['my_signal']}) vs Leg{int(r['other_leg'])} (sig={r['other_signal']}) — {ph_note} — count={int(r['count'])}")
else:
    print("  NONE!")

# ─────────────────────────────────────────────────────────────────────────────
# PART 3: Leg 0 queue-clearing check — 3 cycles pure car
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("PART 3: LEG 0 CYCLE QUEUE CLEARING (3 cycles, pure car, 4-leg sim)")
print("=" * 70)
# Re-run a fresh 3-cycle sim, using the real intersection module (no instrumentation overhead)
rng3 = np.random.default_rng(42)
inter3 = Intersection(config, RATE, 390, {"car": 1.0}, rng3)
leg0_snapshot = []
for t in range(390):
    inter3.step(t)
    leg0 = inter3.legs[0]
    stop_l = leg0.stop_line_position_cells
    q_before = sum(1 for v in leg0.vehicles if v.position_cells < stop_l)
    in_box = sum(1 for v in leg0.vehicles if v.position_cells >= stop_l)
    total = len(leg0.vehicles)
    sig = leg0.signal.state_at(t)
    phase_in_cycle = t % cycle_len
    leg0_snapshot.append((t, sig, q_before, in_box, total, phase_in_cycle))

print(f"\nLeg 0 state at end of each GREEN phase (t%{cycle_len}=={green_len-1}):")
print(f"{'Cycle':>5} {'t':>5} {'Signal':>7} {'Before stop':>12} {'In box':>7} {'Total':>7} {'Cleared?':>10}")
for t, sig, q, ib, tot, phc in leg0_snapshot:
    if phc == green_len - 1:
        cyc = t // cycle_len
        cleared = "✓ CLEARED" if q == 0 else f"✗ {q} LEFT"
        print(f"{cyc:>5} {t:>5} {sig:>7} {q:>12} {ib:>7} {tot:>7} {cleared:>10}")

print(f"\nLeg 0 state at peak of RED phase (t%{cycle_len}=={cycle_len-1}):")
print(f"{'Cycle':>5} {'t':>5} {'Signal':>7} {'Before stop':>12} {'In box':>7} {'Total':>7}")
for t, sig, q, ib, tot, phc in leg0_snapshot:
    if phc == cycle_len - 1:
        cyc = t // cycle_len
        print(f"{cyc:>5} {t:>5} {sig:>7} {q:>12} {ib:>7} {tot:>7}")

print(f"\nLeg 0 throughput: {inter3.natural_exits_count + inter3.forced_crossings_count} exited of {inter3.vehicle_id_counter-1} inserted over 390s")
print(f"Exits/inserted ratio: {(inter3.natural_exits_count + inter3.forced_crossings_count) / max(1, inter3.vehicle_id_counter-1) * 100:.1f}%")
