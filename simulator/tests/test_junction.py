import pytest
import numpy as np
from src.core.junction import Junction, decide_exit_road

def test_junction_validation_success():
    # Valid proportions
    turn_props = {
        "Road_A": {"Road_B": 0.7, "Road_C": 0.15, "Road_D": 0.15}
    }
    j = Junction("J1", ["Road_A"], ["Road_B", "Road_C", "Road_D"], turn_props)
    assert j.junction_id == "J1"
    assert j.incoming_roads == ["Road_A"]
    assert j.outgoing_roads == ["Road_B", "Road_C", "Road_D"]

def test_junction_validation_failure_sum():
    # Proportions do not sum to 1.0
    turn_props = {
        "Road_A": {"Road_B": 0.7, "Road_C": 0.15, "Road_D": 0.20} # Sum is 1.05
    }
    with pytest.raises(ValueError) as excinfo:
        Junction("J1", ["Road_A"], ["Road_B", "Road_C", "Road_D"], turn_props)
    assert "must sum to 1.0" in str(excinfo.value)

def test_junction_validation_failure_missing_incoming():
    # Missing proportions for one incoming road
    turn_props = {
        "Road_A": {"Road_B": 1.0}
    }
    with pytest.raises(ValueError) as excinfo:
        Junction("J1", ["Road_A", "Road_X"], ["Road_B"], turn_props)
    assert "Missing turn proportions for incoming road" in str(excinfo.value)

def test_junction_validation_failure_invalid_outgoing():
    # Outgoing road in proportions is not in the outgoing roads list
    turn_props = {
        "Road_A": {"Road_B": 0.5, "Road_Z": 0.5} # Road_Z is not in list
    }
    with pytest.raises(ValueError) as excinfo:
        Junction("J1", ["Road_A"], ["Road_B", "Road_C"], turn_props)
    assert "is not in outgoing_roads list" in str(excinfo.value)

def test_junction_statistical_distribution():
    # Set up proportions
    turn_props = {
        "Road_A": {"Road_B": 0.7, "Road_C": 0.2, "Road_D": 0.1}
    }
    j = Junction("J1", ["Road_A"], ["Road_B", "Road_C", "Road_D"], turn_props)
    
    rng = np.random.default_rng(12345)
    num_draws = 10000
    counts = {"Road_B": 0, "Road_C": 0, "Road_D": 0}
    
    for _ in range(num_draws):
        chosen = j.decide_exit_road("Road_A", rng)
        counts[chosen] += 1
        
    observed = {k: v / num_draws for k, v in counts.items()}
    expected = {"Road_B": 0.7, "Road_C": 0.2, "Road_D": 0.1}
    
    # Statistical check: observed frequencies should be close to expected
    # For N=10000, std dev of proportion p is sqrt(p*(1-p)/N).
    # For p=0.2, std dev = sqrt(0.16/10000) = 0.004.
    # A tolerance of 0.015 (approx 3.7 std devs) is extremely robust.
    for road in expected:
        assert abs(observed[road] - expected[road]) < 0.015, (
            f"Observed proportion {observed[road]} for {road} is too far "
            f"from expected {expected[road]} (tolerance 0.015)"
        )

def test_standalone_decide_exit_road():
    turn_props = {
        "Road_A": {"Road_B": 0.6, "Road_C": 0.4}
    }
    rng = np.random.default_rng(42)
    chosen = decide_exit_road("Road_A", turn_props, rng)
    assert chosen in ["Road_B", "Road_C"]

def test_grid_builder_network():
    from src.network.grid_builder import build_grid_network
    
    # Build a 2x2 grid, periodic, segments of 10 cells
    net = build_grid_network(rows=2, cols=2, segment_length_cells=10, periodic=True)
    
    # 2 rows, 2 cols = 4 junctions
    assert len(net.junctions) == 4
    
    # In a periodic 2x2 grid:
    # Each junction has 4 incoming and 4 outgoing roads.
    # Total roads: 4 junctions * 4 outgoing roads = 16 roads.
    assert len(net.roads) == 16
    
    for r in range(2):
        for c in range(2):
            j_id = f"J_{r}_{c}"
            assert j_id in net.junctions
            j = net.junctions[j_id]
            assert len(j.incoming_roads) == 4
            assert len(j.outgoing_roads) == 4
            
    # Test open grid (non-periodic)
    net_open = build_grid_network(rows=2, cols=2, segment_length_cells=10, periodic=False)
    assert len(net_open.junctions) == 4
    # In an open 2x2 grid:
    # Roads:
    # Row 0: E_0_0, W_0_0 (2 roads)
    # Row 1: E_1_0, W_1_0 (2 roads)
    # Col 0: S_0_0, N_0_0 (2 roads)
    # Col 1: S_0_1, N_0_1 (2 roads)
    # Total = 8 roads
    assert len(net_open.roads) == 8

