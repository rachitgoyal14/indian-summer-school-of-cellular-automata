from typing import List, Tuple
from src.core.vehicle import Vehicle

def front_gap(vehicle: Vehicle, other_vehicles: List[Vehicle]) -> float:
    """
    Longitudinal gap to nearest vehicle ahead whose lateral position overlaps this vehicle's lateral extent.
    Returns float('inf') if no vehicle ahead in the same lateral path.
    """
    min_gap = float('inf')
    v_left = vehicle.lateral_position_cells
    v_right = vehicle.lateral_position_cells + vehicle.width_cells - 1
    v_front = vehicle.position_cells
    v_back = vehicle.position_cells - vehicle.length_cells + 1
    
    for other in other_vehicles:
        if other.id == vehicle.id:
            continue
            
        o_left = other.lateral_position_cells
        o_right = other.lateral_position_cells + other.width_cells - 1
        
        # Check lateral overlap
        if v_left <= o_right and o_left <= v_right:
            o_back = other.position_cells - other.length_cells + 1
            o_front = other.position_cells
            
            if o_back > v_front:
                gap = o_back - v_front - 1
                if gap < min_gap:
                    min_gap = gap
            elif v_back <= o_front and o_back <= v_front:
                # Longitudinal overlap while laterally overlapping -> collision!
                return 0.0
                
    return min_gap

def lateral_gap(vehicle: Vehicle, other_vehicles: List[Vehicle]) -> Tuple[float, float]:
    """
    Minimum lateral clearance on left and right sides to vehicles overlapping the relevant longitudinal range.
    Returns (gap_left, gap_right).
    If no vehicles on a side, returns float('inf') for that side.
    """
    gap_left = float('inf')
    gap_right = float('inf')
    
    v_back = vehicle.position_cells - vehicle.length_cells + 1
    v_front_future = vehicle.position_cells + vehicle.speed_cells_per_step
    v_left = vehicle.lateral_position_cells
    v_right = vehicle.lateral_position_cells + vehicle.width_cells - 1
    
    for other in other_vehicles:
        if other.id == vehicle.id:
            continue
            
        o_back = other.position_cells - other.length_cells + 1
        o_front_future = other.position_cells + other.speed_cells_per_step
        
        # Check longitudinal overlap over the entire swept path to avoid collisions
        # We consider the union of current and future footprint for safety
        v_min_long = min(v_back, vehicle.position_cells - vehicle.length_cells + 1) # same
        v_max_long = v_front_future
        
        o_min_long = o_back
        o_max_long = o_front_future
        
        if v_min_long <= o_max_long and o_min_long <= v_max_long:
            o_left = other.lateral_position_cells
            o_right = other.lateral_position_cells + other.width_cells - 1
            
            if o_right < v_left:
                g = v_left - o_right - 1
                if g < gap_left:
                    gap_left = float(g)
            elif o_left > v_right:
                g = o_left - v_right - 1
                if g < gap_right:
                    gap_right = float(g)
            else:
                # Laterally and longitudinally overlapping
                return 0.0, 0.0
                
    return gap_left, gap_right


def seepage_lateral_gap(
    vehicle: Vehicle,
    other_vehicles: List[Vehicle]
) -> tuple[float, float]:
    """
    Compute lateral seepage gaps per Fig 6 / Eq 4 geometry.

    Eq 4 (base.pdf): lateral_gap = min(d4, d3)
    where d3, d4 are the clearances on the LEFT and RIGHT side of `vehicle`,
    measured from adjacent stopped vehicles to `vehicle`'s lateral edge.

    We check longitudinal overlap over the swept paths of both vehicles to prevent
    collisions with moving or decelerating neighbors.

    Returns
    -------
    (gap_left, gap_right) : tuple[float, float]
        Raw clearances (cells) — WITHOUT safety margin subtracted.
        The caller (seepage.py) compares these to (vehicle.width_cells +
        lateral_safety_margin_cells) to decide eligibility.
    """
    gap_left = float('inf')   # d4: clearance on left side
    gap_right = float('inf')  # d3: clearance on right side

    v_back = vehicle.position_cells - vehicle.length_cells + 1
    # Seepage advance is at most 2 cells
    v_front_future = vehicle.position_cells + 2
    v_left = vehicle.lateral_position_cells
    v_right = vehicle.lateral_position_cells + vehicle.width_cells - 1

    for other in other_vehicles:
        if other.id == vehicle.id:
            continue

        o_back = other.position_cells - other.length_cells + 1
        o_front_future = other.position_cells + other.speed_cells_per_step

        # Longitudinal overlap check over the swept paths
        if v_back <= o_front_future and o_back <= v_front_future:
            o_left = other.lateral_position_cells
            o_right = other.lateral_position_cells + other.width_cells - 1

            # Determine which side(s) the neighbor affects, using o_left as the
            # primary indicator of which side the neighbor is "from":
            #
            #   o_left < v_left  → neighbor is primarily to our left:
            #     gap_left = max(0, v_left - o_right - 1)
            #     (negative if o_right >= v_left, i.e., touching or overlapping on left → clamp 0)
            #
            #   o_left > v_right → neighbor is primarily to our right:
            #     gap_right = max(0, o_left - v_right - 1)
            #
            #   o_left in [v_left, v_right] → neighbor straddles or sits inside our footprint:
            #     blocks both sides

            if o_left < v_left:
                # Neighbor starts to our LEFT.
                # Compute gap_left = clearance between neighbor's right edge and our left edge.
                d4 = max(0.0, float(v_left - o_right - 1))
                if d4 < gap_left:
                    gap_left = d4
                # If the neighbor also extends past our right edge (wider straddle from the left),
                # it blocks our right side too — block both.
                if o_right > v_right:
                    gap_right = 0.0
            elif o_left > v_right:
                # Neighbor starts fully to our RIGHT.
                # o_left > v_right implies o_right >= o_left > v_right > v_left,
                # so the neighbor cannot also span to our left — only right side affected.
                d3 = max(0.0, float(o_left - v_right - 1))
                if d3 < gap_right:
                    gap_right = d3
            else:
                # o_left in [v_left, v_right]: neighbor starts inside or at our left edge
                # — straddles or fully overlaps — block both sides
                gap_left = 0.0
                gap_right = 0.0

    return gap_left, gap_right


def seepage_longitudinal_gap(
    vehicle: Vehicle,
    front_vehicles: List[Vehicle]
) -> float:
    """
    Compute the longitudinal seepage gap for diagonal forward movement, per Fig 6 / Eq 5.

    Eq 5 (base.pdf): longitudinal_gap = min(d1, d2)
    where d1 is the forward clearance to the first front vehicle and d2 is the
    forward clearance to the second front vehicle (the two vehicles `vehicle`
    would slip between diagonally).

    In practice: given a list of vehicles ahead (at least 2 needed for a
    diagonal gap to exist), compute the minimum of the forward gap to each of
    the two nearest front vehicles whose lateral extents bracket the seeping
    vehicle's path.  If fewer than 2 such vehicles exist, return float('inf')
    (no pair to slip between — check is vacuous).

    Returns
    -------
    float
        Raw minimum forward clearance (cells) — WITHOUT safety margin.
        The caller subtracts longitudinal_safety_margin_cells before checking.
    """
    v_front = vehicle.position_cells
    v_left = vehicle.lateral_position_cells
    v_right = vehicle.lateral_position_cells + vehicle.width_cells - 1

    # Collect all vehicles ahead of this one with their forward gap
    candidates: list[tuple[float, Vehicle]] = []
    for other in front_vehicles:
        if other.id == vehicle.id:
            continue
        o_back = other.position_cells - other.length_cells + 1
        if o_back > v_front:
            d = o_back - v_front - 1  # forward clearance
            candidates.append((d, other))

    if len(candidates) < 2:
        return float('inf')

    # Sort by forward distance — nearest first
    candidates.sort(key=lambda x: x[0])

    # Pick the two nearest front vehicles (d1 and d2 in Fig 6)
    d1 = candidates[0][0]
    d2 = candidates[1][0]

    return min(d1, d2)
