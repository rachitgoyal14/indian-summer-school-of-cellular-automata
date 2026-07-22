import numpy as np
import pytest
from src.core.cell import random_initial_state
from src.core.rule184 import step
from src.analytics.density import density_of, flow_at_step

def test_random_initial_state():
    rng = np.random.default_rng(42)
    length = 100
    density = 0.35
    state = random_initial_state(length, density, rng)
    
    assert len(state) == length
    assert np.all((state == 0) | (state == 1))
    
    # Check that density is exact (rounded to nearest integer of cars)
    expected_cars = int(round(length * density))
    assert np.sum(state == 1) == expected_cars

def test_rule184_periodic_basic():
    # Test that [1, 1, 0, 0] under periodic boundary conditions updates to [1, 0, 1, 0].
    # Let's verify Wolfram Rule 184 step-by-step:
    # i=0: neighbors (0, 1, 1) -> 1
    # i=1: neighbors (1, 1, 0) -> 0
    # i=2: neighbors (1, 0, 0) -> 1
    # i=3: neighbors (0, 0, 1) -> 0
    state = np.array([1, 1, 0, 0], dtype=np.int8)
    next_state = step(state, periodic=True)
    expected = np.array([1, 0, 1, 0], dtype=np.int8)
    np.testing.assert_array_equal(next_state, expected)

def test_rule184_simultaneous_vs_sequential():
    # In a sequential update, a car might move multiple steps or allow a chain reaction.
    # For example, with state [1, 1, 0, 0], if updated sequentially from left to right:
    # i=0: s[1] is 1, so s[0] cannot move.
    # i=1: s[2] is 0, so s[1] moves to s[2]. State becomes [1, 0, 1, 0].
    # i=2: s[3] is 0, so the car that just moved to s[2] moves again to s[3]. State becomes [1, 0, 0, 1].
    #
    # If updated sequentially from right to left:
    # i=1: s[2] is 0, so s[1] moves to s[2]. State becomes [1, 0, 1, 0].
    # i=0: s[1] is now 0 (since it just moved), so s[0] moves to s[1]. State becomes [0, 1, 1, 0].
    #
    # Under correct simultaneous update, the result must be [1, 0, 1, 0].
    # Let's assert our function returns [1, 0, 1, 0], verifying it is truly simultaneous/synchronous.
    state = np.array([1, 1, 0, 0], dtype=np.int8)
    next_state = step(state, periodic=True)
    assert np.array_equal(next_state, [1, 0, 1, 0])

def test_rule184_open_basic():
    # Test open boundary:
    # - Car at last cell exits/disappears (next neighbor is 0).
    # - No new car enters at first cell (prev neighbor is 0).
    
    # State: [1, 1, 1]
    # i=0: s[1]=1 -> stays (1)
    # i=1: s[2]=1 -> stays (1)
    # i=2: exits -> becomes 0
    state = np.array([1, 1, 1], dtype=np.int8)
    assert np.array_equal(step(state, periodic=False), [1, 1, 0])
    
    # State: [1, 1, 0]
    # i=0: s[1]=1 -> stays (1)
    # i=1: s[2]=0 -> moves to 2 (becomes 0, cell 2 becomes 1)
    # i=2: s[1]=1 -> becomes 1
    state = np.array([1, 1, 0], dtype=np.int8)
    assert np.array_equal(step(state, periodic=False), [1, 0, 1])

def test_density_and_flow():
    # State: [1, 1, 0, 0], density should be 0.5
    state = np.array([1, 1, 0, 0], dtype=np.int8)
    assert density_of(state) == 0.5
    
    # [1, 1, 0, 0] -> [1, 0, 1, 0]
    # 1 car moved (the one at index 1 moved to index 2, index 0 stayed at 0).
    # Flow should be 1 / 4 = 0.25
    next_state = np.array([1, 0, 1, 0], dtype=np.int8)
    assert flow_at_step(state, next_state) == 0.25
