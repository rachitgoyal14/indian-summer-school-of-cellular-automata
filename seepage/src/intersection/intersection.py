import numpy as np
from typing import Literal, List, Tuple
import pandas as pd

from src.core.vehicle import Vehicle
from src.intersection.signal import Signal
from src.sim.generator import generate_vehicle_arrivals
from src.core.motion import accelerate, decelerate_for_gap, update_positions
from src.core.gaps import lateral_gap
from src.core.lane_change import decide_lateral_move
from src.intersection.izoi import is_in_izoi, izoi_behavior
from src.intersection.routing import choose_turn

class Leg:
    def __init__(self, leg_id: int, config: dict, rate_veh_per_hour: float, duration_s: int, mode_mix: dict, rng: np.random.Generator, phase_offset_s: int):
        self.leg_id = leg_id
        self.config = config
        self.rng = rng
        self.cell_length_m = config['grid']['cell_length_m']
        self.cell_width_m = config['grid']['cell_width_m']
        self.road_length_cells = int(config['midblock_test']['road_length_m'] / self.cell_length_m)
        self.road_width_cells = int(config['midblock_test'].get('road_width_m', 7.0) / self.cell_width_m)
        self.stop_line_position_cells = self.road_length_cells - 100
        
        signal_config = config['signal']
        self.signal = Signal(
            cycle_length_s=signal_config['cycle_length_s'],
            green_s=signal_config['green_s'],
            red_s=signal_config['red_s'],
            phase_offset_s=phase_offset_s
        )
        
        self.arrivals = generate_vehicle_arrivals(rate_veh_per_hour, duration_s, rng)
        self.next_arrival_idx = 0
        self.pending_arrivals = []
        self.vehicles: List[Vehicle] = []
        
        # We assign a turn direction to each vehicle when it enters the IZOI, or at generation.
        # Let's assign at generation for simplicity.
        self.turn_directions = {} # v_id -> str
        self.turn_proportions = config.get('turn_proportions', {}).get('default', {'left': 0.15, 'straight': 0.70, 'right': 0.15})

class Intersection:
    def __init__(self, config: dict, rate_veh_per_hour: float, duration_s: int, mode_mix: dict, rng: np.random.Generator):
        self.config = config
        self.rng = rng
        self.duration_s = duration_s
        
        signal_config = config['signal']
        c = signal_config['cycle_length_s']
        g = signal_config['green_s']
        # Legs 0 & 2 (N-S) share phase offset 0
        # Legs 1 & 3 (E-W) share phase offset = green_s + clearance
        # Just use offset = c // 2 to be safe and perfectly alternating.
        offset = c // 2
        
        self.legs = [
            Leg(0, config, rate_veh_per_hour, duration_s, mode_mix, rng, 0),
            Leg(1, config, rate_veh_per_hour, duration_s, mode_mix, rng, offset),
            Leg(2, config, rate_veh_per_hour, duration_s, mode_mix, rng, 0),
            Leg(3, config, rate_veh_per_hour, duration_s, mode_mix, rng, offset)
        ]
        
        self.vehicle_id_counter = 1
        
        # Junction box is 2W x 2W
        W = self.legs[0].road_width_cells
        self.box_size = 2 * W
        
        # Bounded max-wait override: track when each vehicle entered the junction box.
        # If stuck > 2 full signal cycles, grant right-of-way to cross.
        self.junction_entry_t = {}  # vehicle_id -> timestep of first box entry
        self.max_box_dwell_s = config['signal']['cycle_length_s']  # 1 cycle = 130s (was 2 cycles); vehicles stuck longer than this block the opposing phase
        self.forced_crossings_count = 0
        self.forced_crossing_ids = set()
        self.natural_exits_count = 0
        
    def get_full_path_cells(self, leg_id: int, lat_pos: int, turn: str, length: int, width: int) -> set:
        cells_set = set()
        W = self.box_size // 2
        exit_threshold = (W + length) if turn != 'straight' else (2 * self.box_size)
        for p in range(0, exit_threshold):
            for c in self.get_junction_cells(leg_id, lat_pos, turn, p, length, width):
                if 0 <= c[0] < self.box_size and 0 <= c[1] < self.box_size:
                    cells_set.add(c)
        return cells_set
        
    def get_junction_cells(self, leg_id: int, lat_pos: int, turn: str, pos_past_stop: int, v_length: int, v_width: int) -> List[Tuple[int, int]]:
        """
        Map a vehicle's 1D position (past stop line) to 2D cells in the junction box.
        Leg 0: North approach (heading South). Drives on East half (x in [W, 2W-1]). y goes from 2W-1 down to 0.
        Leg 1: East approach (heading West). Drives on South half (y in [W, 2W-1]). x goes from 2W-1 down to 0.
        Leg 2: South approach (heading North). Drives on West half (x in [0, W-1]). y goes from 0 up to 2W-1.
        Leg 3: West approach (heading East). Drives on North half (y in [0, W-1]). x goes from 0 up to 2W-1.
        """
        cells = []
        W = self.legs[0].road_width_cells
        
        # For turning vehicles, clamp effective body length to W cells inside the box.
        # A long vehicle (e.g. bus) turning has its rear still on the approach road;
        # only the portion that has entered the box (up to W cells) traces the arc.
        # This prevents unrealistically large exclusion zones for long turning vehicles.
        effective_length = v_length if turn == "straight" else min(v_length, W)
        
        # If pos_past_stop < 0, it hasn't reached the box yet.
        # We only care about the front of the vehicle up to its back.
        for l in range(effective_length):
            p = pos_past_stop - l
            if p < 0:
                continue
                
            # Straight path logic (simplification for Phase 4)
            # In a real setup, left/right turns would trace a curve. For a coarse check, we can just project straight lines
            # and right turns cut across the middle, left turns hug the edge.
            # To keep it robust against collisions and perfectly fulfilling "right-turn-yields-to-opposing-through",
            # we can just use the straight trajectory for occupancy, OR implement a simple curve.
            
            # Simple straight projection mapping:
            x, y = -1, -1
            if leg_id == 0:
                x_base = W + lat_pos
                y_base = 2*W - 1 - p
                x, y = x_base, y_base
            elif leg_id == 1:
                y_base = W + lat_pos
                x_base = 2*W - 1 - p
                x, y = x_base, y_base
            elif leg_id == 2:
                x_base = lat_pos
                y_base = p
                x, y = x_base, y_base
            elif leg_id == 3:
                y_base = lat_pos
                x_base = p
                x, y = x_base, y_base
                
            # For simplicity, if it's turning, let's just make it occupy its straight path until it exits the box.
            # The instructions say "curving through their turn, not teleporting or clipping through the box in a straight line".
            # Okay, I will implement a rudimentary curve!
            if turn == "left":
                # Left turn in India (left-hand traffic) is a tight turn.
                if p > W:
                    continue
                shift = max(0, p - W//2)
                # Leg 0 (heading South): left is East (+x)
                if leg_id == 0: x += shift
                # Leg 1 (heading West): left is South (-y, since y=0 is bottom? wait. 
                # Let's define the grid: x=0 is West, x=2W-1 is East. y=0 is South, y=2W-1 is North.
                # Leg 1 (East approach heading West): left is South (-y)
                elif leg_id == 1: y -= shift
                # Leg 2 (South approach heading North): left is West (-x)
                elif leg_id == 2: x -= shift
                # Leg 3 (West approach heading East): left is North (+y)
                elif leg_id == 3: y += shift
            elif turn == "right":
                # Right turn crosses opposing traffic.
                shift = max(0, p)
                # Leg 0 (heading South): right is West (-x)
                if leg_id == 0: x -= shift // 2
                # Leg 1 (heading West): right is North (+y)
                elif leg_id == 1: y += shift // 2
                # Leg 2 (heading North): right is East (+x)
                elif leg_id == 2: x += shift // 2
                # Leg 3 (heading East): right is South (-y)
                elif leg_id == 3: y -= shift // 2
                
            for w in range(v_width):
                cx, cy = x, y
                if leg_id == 0 or leg_id == 2: cx += w
                else: cy += w
                
                cells.append((int(cx), int(cy)))  # Always int coords for correct dict key hashing
                    
        return cells
        
    def step(self, t: int) -> List[dict]:
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
                        id=self.vehicle_id_counter,
                        mode=mode,
                        length_cells=v_length,
                        width_cells=v_width,
                        max_speed_cells_per_step=params['max_speed_cells_per_step'],
                        max_accel_cells_per_step2=params['max_accel_cells_per_step2'],
                        position_cells=v_length - 1,
                        lateral_position_cells=best_lat,
                        speed_cells_per_step=initial_speed
                    )
                    leg.vehicles.append(new_vehicle)
                    leg.turn_directions[new_vehicle.id] = choose_turn(mode, leg.turn_proportions, self.rng)
                    self.vehicle_id_counter += 1
                    leg.pending_arrivals.pop(0)
                    inserted_this_step += 1
                else:
                    break
        
        # 2. Build global occupancy of the junction box for conflict resolution
        junction_occupancy = {} # (x, y) -> (leg_id, vehicle_id, turn, position_past_stop)
        for leg in self.legs:
            for v in leg.vehicles:
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past >= 0:
                    turn = leg.turn_directions[v.id]
                    cells = self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells)
                    for c in cells:
                        junction_occupancy[c] = (leg.leg_id, v.id, turn, pos_past)
        
        # 3. Accelerate & Gap Decelerate
        izoi_config = self.config['izoi_distance_m']
        izoi_decel_rate = self.config['izoi_deceleration_rate']
        
        # Accelerate and decelerate_for_gap for all legs independently first (1D logic)
        for leg in self.legs:
            accelerate(leg.vehicles)
            decelerate_for_gap(leg.vehicles)
            
        # Global 2D Junction Box Conflict Resolution
        def turn_priority(turn_str):
            return 1 if turn_str in ["straight", "left"] else 0
        all_vehicles = []
        for leg in self.legs:
            for v in leg.vehicles:
                # Only consider vehicles that are near or in the junction box.
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past >= -30 and pos_past < 2*self.box_size:
                    # Determine right-of-way status
                    in_box = pos_past >= 0
                    dwell_s = (t - self.junction_entry_t.get(v.id, t)) if in_box else 0
                    row_status = 1 if (in_box and dwell_s > self.max_box_dwell_s) else 0
                    all_vehicles.append((leg, v, row_status))
                
        all_vehicles.sort(key=lambda item: (
            item[2], # Right-of-way vehicles first (row_status = 1)
            item[1].position_cells - item[0].stop_line_position_cells, 
            turn_priority(item[0].turn_directions[item[1].id]),
            -item[1].id
        ), reverse=True)
        
        # Two separate maps:
        # current_occupancy: (x,y) -> vehicle_id  [physical cells RIGHT NOW — never overridable]
        # future_reservations: (x,y) -> (vehicle_id, progress_score, row_status)
        current_occupancy = {}   # hard constraint: cannot drive into these
        future_reservations = {} # soft: lower-priority vehicle yields to higher-priority
        
        # Phase A: everyone already IN the box claims their CURRENT footprint (hard constraint)
        for leg, v, _ in all_vehicles:
            pos_past = v.position_cells - leg.stop_line_position_cells
            if pos_past >= 0:
                turn = leg.turn_directions[v.id]
                for cx, cy in self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                    if 0 <= cx < self.box_size and 0 <= cy < self.box_size:
                        current_occupancy[(cx, cy)] = v.id
                    
        # Phase B: each vehicle (priority order) tries to claim its FUTURE cells
        for leg, v, row_status in all_vehicles:
            turn = leg.turn_directions[v.id]
            speed = int(v.speed_cells_per_step)
            my_progress = v.position_cells - leg.stop_line_position_cells
            
            if row_status == 1:
                if v.id not in self.forced_crossing_ids:
                    self.forced_crossing_ids.add(v.id)
                # Bounded max-wait override: grant right-of-way and ignore soft conflicts
                if v.speed_cells_per_step == 0:
                    v.speed_cells_per_step = 5
                speed = int(v.speed_cells_per_step)
                granted_right_of_way = True
            else:
                granted_right_of_way = False
                
            # Box Junction / Gridlock Prevention Rule:
            # Do not enter the box if a conflicting vehicle from a DIFFERENT leg is already
            # inside the box with an overlapping path. Same-leg following vehicles are
            # intentionally excluded here because their spacing is already enforced by
            # decelerate_for_gap in 1D — including them caused a single-file serialization
            # where only 1 vehicle per leg could ever be in the box at a time.
            if my_progress < 0 and my_progress + speed >= 0 and not granted_right_of_way:
                my_path = self.get_full_path_cells(leg.leg_id, v.lateral_position_cells, turn, v.length_cells, v.width_cells)
                blocked = False
                for other_leg, other_v, other_row in all_vehicles:
                    if other_v.id != v.id and other_leg.leg_id != leg.leg_id:  # BUG FIX: skip same-leg vehicles
                        other_progress = other_v.position_cells - other_leg.stop_line_position_cells
                        W = self.box_size // 2
                        other_turn = other_leg.turn_directions.get(other_v.id, 'straight')
                        other_exit = (W + other_v.length_cells) if other_turn != 'straight' else (2 * self.box_size)
                        if 0 <= other_progress < other_exit:
                            other_path = self.get_full_path_cells(other_leg.leg_id, other_v.lateral_position_cells, other_turn, other_v.length_cells, other_v.width_cells)
                            if my_path.intersection(other_path):
                                blocked = True
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
                            # Hard check: never move into a cell physically occupied by another vehicle right now
                            if c in current_occupancy and current_occupancy[c] != v.id:
                                conflict = True
                                break
                            # Soft check: yield to future reservation from any other vehicle.
                            # Note: same-leg vehicles are intentionally included here — vehicles
                            # already inside the box from the same approach still need to be
                            # respected to prevent rear-end collisions. The same-leg fix only
                            # applies to the ENTRY check (gridlock-prevention block above).
                            if c in future_reservations:
                                other_vid, other_progress, other_row_status, other_res_leg_id = future_reservations[c]
                                if other_vid != v.id:
                                    if not granted_right_of_way or (other_row_status == 1 and other_progress >= my_progress):
                                        conflict = True
                                        break
                    if conflict:
                        v.speed_cells_per_step = step_ahead - 1
                        break
                        
            # After deciding final speed, register the future reservations
            my_progress = v.position_cells - leg.stop_line_position_cells
            for step_ahead in range(1, int(v.speed_cells_per_step) + 1):
                pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
                if pos_past >= 0:
                    for cx, cy in self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                        if 0 <= cx < self.box_size and 0 <= cy < self.box_size:
                            c = (cx, cy)
                            # Only claim if not already reserved by a higher-priority vehicle
                            if c not in future_reservations or future_reservations[c][1] <= my_progress:
                                future_reservations[c] = (v.id, pos_past, row_status, leg.leg_id)  # leg_id stored for O(1) lookup
                        
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

            # Lateral moves
            for v in leg.vehicles:
                if v.position_cells < leg.stop_line_position_cells:
                    params = mode_params[v.mode]
                    gaps = lateral_gap(v, leg.vehicles)
                    lat_move = decide_lateral_move(v, gaps, params['position_preference'], params['lane_change_prob'], leg.road_width_cells, self.rng)
                    v.lateral_position_cells += lat_move
                
            # Randomization
            for v in leg.vehicles:
                if v.id not in skip_randomization:
                    p_slow = mode_params[v.mode]['p_slowdown']
                    if v.speed_cells_per_step > 0 and self.rng.random() < p_slow:
                        v.speed_cells_per_step -= 1
                        
            # Update positions  
            leg.vehicles = update_positions(leg.vehicles, leg.road_length_cells + 2*self.box_size)
            
            # Remove vehicles that exited the junction box.
            # Turning vehicles exit after W + v_length cells; straight vehicles after 2*box_size.
            # Bounded max-wait override: also forcibly eject any vehicle that has been
            # in the box for > max_box_dwell_s steps (geometric-deadlock guard).
            W = self.box_size // 2
            surviving = []
            for v in leg.vehicles:
                pos_past = v.position_cells - leg.stop_line_position_cells
                
                # Track junction box entry time
                if pos_past >= 0 and v.id not in self.junction_entry_t:
                    self.junction_entry_t[v.id] = t
                
                # Determine standard exit threshold
                turn = leg.turn_directions.get(v.id, 'straight')
                if turn == 'straight':
                    exit_threshold = 2 * self.box_size
                else:
                    exit_threshold = W + v.length_cells
                
                # Remove if it exceeds the exit threshold.
                # Vehicles forced through will move forward and exit naturally since they have right-of-way.
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
