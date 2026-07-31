import numpy as np

def step(state: np.ndarray, periodic: bool = True) -> np.ndarray:
    """
    Applies one synchronous Rule 184 update to the state array and returns the new state.
    Does not mutate the input state array.
    
    If periodic is True:
        Uses periodic boundary conditions (index wraps around).
    If periodic is False:
        Uses open boundary conditions (cars exit at the end, and no new cars enter at the start).
    """
    if state.ndim != 1:
        raise ValueError("State must be a 1D NumPy array")
    
    if periodic:
        prev_neighbor = np.roll(state, 1)
        next_neighbor = np.roll(state, -1)
    else:
        prev_neighbor = np.concatenate(([0], state[:-1]))
        next_neighbor = np.concatenate((state[1:], [0]))
        
    # Rule 184 synchronous update logic:
    # - A cell with a car (1) stays 1 if its next neighbor is 1, else becomes 0 (moves forward).
    # - A cell without a car (0) becomes 1 if its previous neighbor is 1, else stays 0.
    new_state = np.where(state == 1, next_neighbor, prev_neighbor).astype(np.int8)
    return new_state
