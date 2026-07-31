import numpy as np

def random_initial_state(length: int, density: float, rng: np.random.Generator) -> np.ndarray:
    """
    Returns a random 0/1 NumPy array of the specified length where exactly 
    round(length * density) cells are occupied by cars (represented as 1).
    Other cells are empty (represented as 0).
    """
    if length <= 0:
        raise ValueError("Length must be greater than 0")
    if not (0.0 <= density <= 1.0):
        raise ValueError("Density must be between 0.0 and 1.0 inclusive")
    
    num_cars = int(round(length * density))
    num_cars = max(0, min(num_cars, length)) # Bound check
    
    state = np.zeros(length, dtype=np.int8)
    if num_cars > 0:
        indices = rng.choice(length, size=num_cars, replace=False)
        state[indices] = 1
        
    return state
