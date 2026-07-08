import numpy as np
from typing import List
from src.core.vehicle import Vehicle

class Road:
    """
    Represents a 1D straight road segment in the CA model.
    """
    def __init__(self, config: dict):
        self.cell_length_m = config['grid']['cell_length_m']
        self.road_length_m = config['midblock_test']['road_length_m']
        self.road_length_cells = int(self.road_length_m / self.cell_length_m)

    def occupancy_array(self, vehicles: List[Vehicle]) -> np.ndarray:
        """
        Returns a boolean array marking which cells are occupied.
        The position_cells of a vehicle is its front bumper.
        It occupies cells from (position_cells - length_cells + 1) to position_cells.
        """
        occupancy = np.zeros(self.road_length_cells, dtype=bool)
        for v in vehicles:
            front = v.position_cells
            back = front - v.length_cells + 1
            
            # Clip bounds to the road length
            start_idx = max(0, back)
            end_idx = min(self.road_length_cells - 1, front)
            
            if start_idx <= end_idx and end_idx >= 0 and start_idx < self.road_length_cells:
                occupancy[start_idx:end_idx + 1] = True
                
        return occupancy
