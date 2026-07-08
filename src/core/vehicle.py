from dataclasses import dataclass

@dataclass
class Vehicle:
    """
    Represents a vehicle in the Cellular Automata simulation.
    """
    id: int
    mode: str
    length_cells: int
    width_cells: int
    max_speed_cells_per_step: int
    max_accel_cells_per_step2: int
    position_cells: int = 0
    lateral_position_cells: int = 0
    speed_cells_per_step: int = 0
