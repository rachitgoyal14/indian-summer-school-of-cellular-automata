import pytest
from src.intersection.signal import Signal

def test_signal_invalid_init():
    with pytest.raises(ValueError):
        Signal(cycle_length_s=90, green_s=50, red_s=50)

def test_signal_state_at():
    # 130 cycle, 30 green, 100 red
    sig = Signal(cycle_length_s=130, green_s=30, red_s=100)
    
    assert sig.state_at(0) == "green"
    assert sig.state_at(15) == "green"
    assert sig.state_at(29.9) == "green"
    assert sig.state_at(30) == "red"
    assert sig.state_at(80) == "red"
    assert sig.state_at(129.9) == "red"
    assert sig.state_at(130) == "green"
    assert sig.state_at(145) == "green"
    
def test_signal_offset():
    # 90 cycle, 45 green, 45 red, offset 45
    sig = Signal(cycle_length_s=90, green_s=45, red_s=45, phase_offset_s=45)
    
    # At t=0, effective time is -45 = 45 -> "red"
    assert sig.state_at(0) == "red"
    # At t=44.9, effective is 89.9 -> "red"
    assert sig.state_at(44.9) == "red"
    # At t=45, effective is 0 -> "green"
    assert sig.state_at(45) == "green"
    assert sig.state_at(89.9) == "green"
    assert sig.state_at(90) == "red"
