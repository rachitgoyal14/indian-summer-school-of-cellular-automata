"""
Seepage behavior — Algorithm 3 from Singh & Ramachandra Rao (2023).

Seepage is the behavior where small vehicles (two-wheelers, three-wheelers)
filter laterally or diagonally through gaps between larger stopped vehicles
during a red signal phase, to advance closer to the stop line.

Reference equations from base.pdf:
  Eq 4: lateral_gap  = min(d4, d3)   [d3,d4 = lateral clearances, Fig 6]
  Eq 5: longitudinal_gap = min(d1, d2) [d1,d2 = forward clearances, Fig 6]

Algorithm 3 (base.pdf, p.9):
  for v = 1 : number_of_vehicles:
    if left_gap(v) > size(v) + safety_distance:
        seep left
    elif right_gap(v) > size(v) + safety_distance:
        seep right
    elif lateral_spread_of_front_vehicles > size(v) + safety_distance:
        seep diagonally between two front vehicles
    else:
        reduce speed and stop slowly
"""

from typing import List, Literal
import numpy as np

from src.core.vehicle import Vehicle
from src.core.gaps import seepage_lateral_gap, seepage_longitudinal_gap
from src.intersection.izoi import is_in_izoi
from src.intersection.izoi import izoi_behavior


SeepageAction = Literal["seep_left", "seep_right", "seep_diagonal", "stopped"]


def is_seepage_eligible(
    vehicle: Vehicle,
    signal_state: str,
    stop_line_position_cells: int,
    izoi_distance_cells: int,
    seepage_eligible_modes: list[str],
) -> bool:
    """
    Gate function for seepage eligibility per Algorithm 3's conditions.

    A vehicle is eligible for seepage if and only if ALL of:
    1. It is inside the IZOI (uses Phase 3's is_in_izoi — no duplication).
    2. The signal is RED (uses signal state_at — no duplication).
    3. Its mode is in the configurable seepage_eligible_modes list.

    Cars and buses are NEVER eligible regardless of gap availability —
    this is consistent with the paper's explicit description of seepage
    as a small-vehicle (two-wheeler, three-wheeler) behavior.

    Parameters
    ----------
    vehicle : Vehicle
    signal_state : str
        "red" or "green" from signal.state_at(t).
    stop_line_position_cells : int
    izoi_distance_cells : int
    seepage_eligible_modes : list[str]
        Configurable list, default ["two_wheeler", "three_wheeler"].

    Returns
    -------
    bool
    """
    # Gate 1: signal must be red
    if signal_state != "red":
        return False
    # Gate 2: vehicle must be in IZOI
    if not is_in_izoi(vehicle, stop_line_position_cells, izoi_distance_cells):
        return False
    # Gate 3: mode eligibility (explicit — cars and buses are never eligible)
    if vehicle.mode not in seepage_eligible_modes:
        return False
    return True


def attempt_seepage(
    vehicle: Vehicle,
    neighbors: List[Vehicle],
    config: dict,
    izoi_decel_rate: int,
    stop_line_position_cells: int,
    rng: np.random.Generator,
    occupied_cells: set | None = None,
) -> SeepageAction:
    """
    Attempt seepage for an eligible vehicle, following Algorithm 3's priority order exactly.

    Priority order (Algorithm 3, base.pdf p.9):
      1. Seep LEFT  if lateral gap on left  > vehicle_width + lateral_safety_margin
      2. Seep RIGHT if lateral gap on right > vehicle_width + lateral_safety_margin
      3. Seep DIAGONALLY between two front vehicles if longitudinal gap > longitudinal_safety_margin
      4. Reduce speed and stop (apply existing IZOI deceleration — no code duplication)

    IMPORTANT: When a seep move is performed, we set speed_cells_per_step = advance
    to record the seep distance. To prevent update_positions() from double-counting
    the movement, sim_loop.py zeroes out speed for seeping vehicles before calling
    update_positions(), then restores it for correct logging.

    Parameters
    ----------
    vehicle : Vehicle
        The eligible vehicle attempting seepage.
    neighbors : List[Vehicle]
        All other vehicles on the same leg (used for gap computation).
    config : dict
        Full simulation config dict.
    izoi_decel_rate : int
        Field-observed deceleration rate (for the "stopped" fallback branch).
    stop_line_position_cells : int
    rng : np.random.Generator
        Random number generator (reserved for future stochastic extensions).
    occupied_cells : set or None
        Set of (position_cells, lateral_position_cells) cells already claimed by
        vehicles in the current timestep.

    Returns
    -------
    SeepageAction
        One of: "seep_left", "seep_right", "seep_diagonal", "stopped"
    """
    if occupied_cells is None:
        occupied_cells = set()

    # Temporarily remove own footprint to prevent self-blocking
    old_pos = vehicle.position_cells
    old_lat = vehicle.lateral_position_cells
    own_cells = []
    for x in range(old_pos - vehicle.length_cells + 1, old_pos + 1):
        for y in range(old_lat, old_lat + vehicle.width_cells):
            cell = (x, y)
            if cell in occupied_cells:
                occupied_cells.remove(cell)
                own_cells.append(cell)

    lat_margin = config.get("lateral_safety_margin_cells", 0.5)
    long_margin = config.get("longitudinal_safety_margin_cells", 1)
    advance_map = config.get("seepage_advance_cells_per_step", {})
    advance = advance_map.get(vehicle.mode, 1)

    road_width_cells = int(
        config["midblock_test"].get("road_width_m", 7.0)
        / config["grid"]["cell_width_m"]
    )

    # Compute gap values per Eq 4 and Eq 5
    gap_left, gap_right = seepage_lateral_gap(vehicle, neighbors)
    long_gap = seepage_longitudinal_gap(vehicle, neighbors)
    # NOTE: we intentionally do NOT cap long_gap with front_gap() here.
    # front_gap() returns 0.0 for ANY laterally-overlapping vehicle at the same
    # longitudinal position (side-by-side traffic), which would incorrectly block
    # diagonal seepage for vehicles with lateral neighbors alongside them.
    # The is_dest_clear() check below provides the correct safety guard by
    # checking whether the destination footprint cells are actually occupied.

    # Threshold: vehicle must fit (width) plus safety margin on each side
    required_lateral = vehicle.width_cells + lat_margin

    # Helper function to check if the new footprint is clear of other vehicles
    def is_dest_clear(new_p, new_l):
        for x in range(new_p - vehicle.length_cells + 1, new_p + 1):
            for y in range(new_l, new_l + vehicle.width_cells):
                if (x, y) in occupied_cells:
                    return False
        return True

    # Helper function to commit a successful seep move
    def commit_seep(new_p, new_l, action):
        vehicle.lateral_position_cells = new_l
        vehicle.position_cells = new_p
        vehicle.speed_cells_per_step = advance
        # Add new footprint to occupied_cells
        for x in range(new_p - vehicle.length_cells + 1, new_p + 1):
            for y in range(new_l, new_l + vehicle.width_cells):
                occupied_cells.add((x, y))
        return action

    # ------------------------------------------------------------------
    # Branch 1: Seep LEFT
    # ------------------------------------------------------------------
    if gap_left >= required_lateral:
        new_lat = vehicle.lateral_position_cells - 1
        if new_lat >= 0:
            new_pos = min(
                vehicle.position_cells + advance,
                stop_line_position_cells - 1
            )
            if is_dest_clear(new_pos, new_lat):
                return commit_seep(new_pos, new_lat, "seep_left")

    # ------------------------------------------------------------------
    # Branch 2: Seep RIGHT
    # ------------------------------------------------------------------
    if gap_right >= required_lateral:
        new_lat = vehicle.lateral_position_cells + 1
        if new_lat + vehicle.width_cells - 1 < road_width_cells:
            new_pos = min(
                vehicle.position_cells + advance,
                stop_line_position_cells - 1
            )
            if is_dest_clear(new_pos, new_lat):
                return commit_seep(new_pos, new_lat, "seep_right")

    # ------------------------------------------------------------------
    # Branch 3: Seep DIAGONALLY between two front vehicles
    # ------------------------------------------------------------------
    usable_long_gap = long_gap - long_margin
    if usable_long_gap > 0:
        new_pos = min(
            vehicle.position_cells + advance,
            stop_line_position_cells - 1
        )
        new_lat = vehicle.lateral_position_cells
        if is_dest_clear(new_pos, new_lat):
            return commit_seep(new_pos, new_lat, "seep_diagonal")

    # ------------------------------------------------------------------
    # Branch 4: Stop — apply existing IZOI deceleration
    # ------------------------------------------------------------------
    # Restore own footprint since seepage failed
    for cell in own_cells:
        occupied_cells.add(cell)

    gap_to_stop = stop_line_position_cells - vehicle.position_cells - 1
    min_gap = min(vehicle.speed_cells_per_step, max(0, gap_to_stop))
    izoi_behavior(vehicle, "red", izoi_decel_rate, min_gap)
    return "stopped"
