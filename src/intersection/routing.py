import numpy as np
from typing import Literal

def choose_turn(mode: str, turn_proportions: dict[str, float], rng: np.random.Generator) -> Literal["left", "straight", "right"]:
    """
    Choose a turning direction based on the provided turn proportions.
    Validates that the proportions sum to 1.0.
    """
    total = sum(turn_proportions.values())
    if not np.isclose(total, 1.0):
        raise ValueError(f"Turn proportions must sum to 1.0, got {total}")
        
    directions = ["left", "straight", "right"]
    probs = [turn_proportions.get(d, 0.0) for d in directions]
    
    return rng.choice(directions, p=probs)
