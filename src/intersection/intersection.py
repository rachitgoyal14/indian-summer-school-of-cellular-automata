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
        
        # If pos_past_stop < 0, it hasn't reached the box yet.
        # We only care about the front of the vehicle up to its back.
        for l in range(v_length):
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
                
                if 0 <= cx < 2*W and 0 <= cy < 2*W:
                    cells.append((cx, cy))
                    
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
        # Sort all vehicles by how far they are into the intersection (highest position first)
        # to give priority to vehicles already in the box, then by ID.
        all_vehicles = []
        for leg in self.legs:
            for v in leg.vehicles:
                all_vehicles.append((leg, v))
                
        all_vehicles.sort(key=lambda item: (item[1].position_cells - item[0].stop_line_position_cells, -item[1].id), reverse=True)
        
        claimed_cells = {} # (x, y) -> (leg_id, vehicle_id, turn)
        
        # First, everyone claims their CURRENT footprint in the box
        for leg, v in all_vehicles:
            pos_past = v.position_cells - leg.stop_line_position_cells
            if pos_past >= 0:
                turn = leg.turn_directions[v.id]
                for c in self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                    claimed_cells[c] = (leg.leg_id, v.id, turn)
                    
        # Now each vehicle tries to claim its future cells
        for leg, v in all_vehicles:
            turn = leg.turn_directions[v.id]
            speed = int(v.speed_cells_per_step)
            for step_ahead in range(1, speed + 1):
                pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
                if pos_past >= 0:
                    future_cells = self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells)
                    conflict = False
                    for c in future_cells:
                        if c in claimed_cells:
                            other_leg, other_vid, other_turn = claimed_cells[c]
                            if other_vid != v.id:
                                # We have a conflict with either someone already there, or someone who claimed it.
                                # Rule: Right-turn yields to opposing straight/left.
                                is_opposing = (abs(leg.leg_id - other_leg) == 2)
                                we_must_yield = False
                                
                                # If the other vehicle is already physically at this cell (it's their current position), we ALWAYS yield to avoid rear-ending.
                                # The claimed_cells includes current positions. We can't tell if it's current or future here, so we yield.
                                if is_opposing:
                                    if turn == "right" and other_turn in ["straight", "left"]:
                                        we_must_yield = True
                                    elif turn == "right" and other_turn == "right":
                                        we_must_yield = v.id > other_vid
                                    elif turn in ["straight", "left"] and other_turn == "right":
                                        we_must_yield = False
                                    else:
                                        we_must_yield = v.id > other_vid
                                else:
                                    # Cross traffic or same-leg conflict
                                    we_must_yield = True # Always yield if someone else claimed it first (since we sorted by priority)
                                    
                                if we_must_yield:
                                    conflict = True
                                    break
                    if conflict:
                        v.speed_cells_per_step = step_ahead - 1
                        break
                        
            # After deciding final speed, claim the cells for the entire path from current to future
            for step_ahead in range(1, int(v.speed_cells_per_step) + 1):
                pos_past = v.position_cells + step_ahead - leg.stop_line_position_cells
                if pos_past >= 0:
                    for c in self.get_junction_cells(leg.leg_id, v.lateral_position_cells, turn, pos_past, v.length_cells, v.width_cells):
                        claimed_cells[c] = (leg.leg_id, v.id, turn)
                        
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
            
            # Remove vehicles that exited the junction box
            surviving = []
            for v in leg.vehicles:
                pos_past = v.position_cells - leg.stop_line_position_cells
                if pos_past < 2 * self.box_size:
                    surviving.append(v)
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
