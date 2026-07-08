import numpy as np
from typing import List

def generate_vehicle_arrivals(rate_veh_per_hour: float, duration_s: int, rng: np.random.Generator) -> List[float]:
    """
    Returns arrival timestamps drawn from an exponential (Poisson process) headway distribution.
    """
    if rate_veh_per_hour <= 0:
        return []
        
    rate_veh_per_s = rate_veh_per_hour / 3600.0
    
    arrivals = []
    current_time = 0.0
    while current_time < duration_s:
        # Inter-arrival time from exponential distribution
        inter_arrival = rng.exponential(1.0 / rate_veh_per_s)
        current_time += inter_arrival
        if current_time < duration_s:
            arrivals.append(current_time)
            
    return arrivals
