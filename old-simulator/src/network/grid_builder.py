import os
import sys
import numpy as np
from src.core.network import Road, Network
from src.core.junction import Junction

def build_grid_network(rows: int, cols: int, segment_length_cells: int, 
                       periodic: bool = True, spacing: float = 200.0,
                       straight_prop: float = 0.7, left_prop: float = 0.15, right_prop: float = 0.15) -> Network:
    """
    Constructs a rectangular grid of connected junctions with road segments of configurable length.
    
    Args:
        rows: Number of junction rows.
        cols: Number of junction columns.
        segment_length_cells: Length of each road segment in cells.
        periodic: If True, wraps boundaries toroidally. If False, roads terminate at grid edges.
        spacing: Spatial distance between adjacent junctions (for rendering coords).
        straight_prop: Proportion of cars going straight.
        left_prop: Proportion of cars turning left.
        right_prop: Proportion of cars turning right.
    """
    if rows <= 0 or cols <= 0:
        raise ValueError("Grid rows and cols must be greater than 0")
        
    net = Network()
    
    # 1. Create junction coordinates and dictionary
    # Coordinates are structured: x = col * spacing, y = row * spacing
    junction_coords = {}
    for r in range(rows):
        for c in range(cols):
            j_id = f"J_{r}_{c}"
            junction_coords[j_id] = (float(c * spacing), float(r * spacing))
            
    # Helper to check if a grid cell (r, c) is valid
    def is_valid(r, c):
        if periodic:
            return True
        return 0 <= r < rows and 0 <= c < cols
        
    def get_coords(r, c):
        # Wraps coordinates toroidally if periodic
        r_wrapped = r % rows
        c_wrapped = c % cols
        return junction_coords[f"J_{r_wrapped}_{c_wrapped}"]

    # 2. Build roads
    # For each cell in the grid, we potentially have 4 directions of roads:
    # - Eastbound (E): from (r, c) to (r, c+1)
    # - Westbound (W): from (r, c+1) to (r, c)
    # - Southbound (S): from (r, c) to (r+1, c)
    # - Northbound (N): from (r+1, c) to (r, c)
    
    # We collect roads by their IDs
    road_objects = {}
    
    for r in range(rows):
        for c in range(cols):
            # Eastbound & Westbound between (r, c) and (r, c+1)
            if is_valid(r, c+1) and (periodic or c < cols - 1):
                c_next = (c + 1) % cols
                e_id = f"R_E_{r}_{c}"
                w_id = f"R_W_{r}_{c}"
                
                road_objects[e_id] = Road(
                    road_id=e_id,
                    length=segment_length_cells,
                    start_coord=get_coords(r, c),
                    end_coord=get_coords(r, c_next),
                    periodic=False
                )
                road_objects[w_id] = Road(
                    road_id=w_id,
                    length=segment_length_cells,
                    start_coord=get_coords(r, c_next),
                    end_coord=get_coords(r, c),
                    periodic=False
                )
                
            # Southbound & Northbound between (r, c) and (r+1, c)
            if is_valid(r+1, c) and (periodic or r < rows - 1):
                r_next = (r + 1) % rows
                s_id = f"R_S_{r}_{c}"
                n_id = f"R_N_{r}_{c}"
                
                road_objects[s_id] = Road(
                    road_id=s_id,
                    length=segment_length_cells,
                    start_coord=get_coords(r, c),
                    end_coord=get_coords(r_next, c),
                    periodic=False
                )
                road_objects[n_id] = Road(
                    road_id=n_id,
                    length=segment_length_cells,
                    start_coord=get_coords(r_next, c),
                    end_coord=get_coords(r, c),
                    periodic=False
                )
                
    # Add all roads to network
    for road in road_objects.values():
        net.add_road(road)

    # 3. Create junctions and turn proportions
    for r in range(rows):
        for c in range(cols):
            j_id = f"J_{r}_{c}"
            
            # Incoming roads to J_{r}_{c}:
            # Eastbound from left: R_E_{r}_{(c-1)%cols}
            # Westbound from right: R_W_{r}_{c}
            # Southbound from above: R_S_{(r-1)%rows}_{c}
            # Northbound from below: R_N_{r}_{c}
            
            # Outgoing roads from J_{r}_{c}:
            # Eastbound to right: R_E_{r}_{c}
            # Westbound to left: R_W_{r}_{(c-1)%cols}
            # Southbound to below: R_S_{r}_{c}
            # Northbound to above: R_N_{(r-1)%rows}_{c}
            
            incoming = []
            outgoing = []
            
            # Left neighbor
            c_prev = (c - 1) % cols
            re_left = f"R_E_{r}_{c_prev}"
            rw_left = f"R_W_{r}_{c_prev}"
            if re_left in road_objects: incoming.append(re_left)
            if rw_left in road_objects: outgoing.append(rw_left)
            
            # Right neighbor
            re_right = f"R_E_{r}_{c}"
            rw_right = f"R_W_{r}_{c}"
            if rw_right in road_objects: incoming.append(rw_right)
            if re_right in road_objects: outgoing.append(re_right)
            
            # Top neighbor
            r_prev = (r - 1) % rows
            rs_top = f"R_S_{r_prev}_{c}"
            rn_top = f"R_N_{r_prev}_{c}"
            if rs_top in road_objects: incoming.append(rs_top)
            if rn_top in road_objects: outgoing.append(rn_top)
            
            # Bottom neighbor
            rs_bottom = f"R_S_{r}_{c}"
            rn_bottom = f"R_N_{r}_{c}"
            if rn_bottom in road_objects: incoming.append(rn_bottom)
            if rs_bottom in road_objects: outgoing.append(rs_bottom)
            
            # Build turn proportions
            turn_props = {}
            for r_in in incoming:
                # Determine direction of incoming road
                # and map to straight/left/right targets
                targets = {}
                
                # Default behavior
                if r_in.startswith("R_E_"): # Eastbound (going right)
                    straight = f"R_E_{r}_{c}"
                    left = f"R_N_{(r-1)%rows}_{c}"
                    right = f"R_S_{r}_{c}"
                elif r_in.startswith("R_W_"): # Westbound (going left)
                    straight = f"R_W_{r}_{(c-1)%cols}"
                    left = f"R_S_{r}_{c}"
                    right = f"R_N_{(r-1)%rows}_{c}"
                elif r_in.startswith("R_S_"): # Southbound (going down)
                    straight = f"R_S_{r}_{c}"
                    left = f"R_E_{r}_{c}"
                    right = f"R_W_{r}_{(c-1)%cols}"
                elif r_in.startswith("R_N_"): # Northbound (going up)
                    straight = f"R_N_{(r-1)%rows}_{c}"
                    left = f"R_W_{r}_{(c-1)%cols}"
                    right = f"R_E_{r}_{c}"
                else:
                    continue
                
                # Check which of straight/left/right actually exist in outgoing roads
                candidates = []
                props = []
                
                if straight in outgoing:
                    candidates.append(straight)
                    props.append(straight_prop)
                if left in outgoing:
                    candidates.append(left)
                    props.append(left_prop)
                if right in outgoing:
                    candidates.append(right)
                    props.append(right_prop)
                    
                # Normalize probabilities if some targets are missing (for boundary edges)
                total_p = sum(props)
                if total_p > 0:
                    normalized_props = [p / total_p for p in props]
                    turn_props[r_in] = {candidates[i]: normalized_props[i] for i in range(len(candidates))}
                else:
                    # If no valid outgoing road exists, the car exits (handled as None target)
                    turn_props[r_in] = {}
            
            # Instantiate junction
            # We filter incoming/outgoing roads to keep validation happy
            j_obj = Junction(
                junction_id=j_id,
                incoming_roads=incoming,
                outgoing_roads=outgoing,
                turn_proportions=turn_props
            )
            net.add_junction(j_obj)
            
    return net
