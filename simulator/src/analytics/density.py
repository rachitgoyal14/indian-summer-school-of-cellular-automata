import numpy as np

def density_of(state: np.ndarray) -> float:
    """
    Returns the density of the state, i.e., the fraction of occupied cells.
    """
    if len(state) == 0:
        return 0.0
    return float(np.mean(state == 1))

def flow_at_step(prev_state: np.ndarray, next_state: np.ndarray) -> float:
    """
    Returns the flow at the current step.
    Flow is defined as the fraction of cells where a car was present in 
    prev_state (1) and successfully moved to the next cell in next_state,
    leaving the previous cell empty (0).
    """
    if len(prev_state) == 0:
        return 0.0
    # In synchronous Rule 184, a car can only move to a cell if that cell was empty in prev_state.
    # Therefore, a car at index i can only move if next_state[i] becomes 0 (since no other car 
    # can enter index i while it is occupied).
    moved = (prev_state == 1) & (next_state == 0)
    return float(np.mean(moved))
