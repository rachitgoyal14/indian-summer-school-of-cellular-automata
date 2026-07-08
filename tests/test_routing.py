import pytest
import numpy as np
from src.intersection.routing import choose_turn

def test_routing_sum_validation():
    rng = np.random.default_rng(42)
    # Valid
    choose_turn('car', {'left': 0.2, 'straight': 0.6, 'right': 0.2}, rng)
    
    # Invalid (sum != 1.0)
    with pytest.raises(ValueError):
        choose_turn('car', {'left': 0.2, 'straight': 0.5, 'right': 0.2}, rng)

def test_routing_distribution():
    rng = np.random.default_rng(42)
    props = {'left': 0.15, 'straight': 0.70, 'right': 0.15}
    N = 5000
    counts = {'left': 0, 'straight': 0, 'right': 0}
    
    for _ in range(N):
        t = choose_turn('car', props, rng)
        counts[t] += 1
        
    for k, p in props.items():
        observed = counts[k] / N
        assert abs(observed - p) <= 0.05, f"Turn '{k}' out of tolerance: {observed} vs {p}"
