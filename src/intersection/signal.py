from typing import Literal

class Signal:
    def __init__(self, cycle_length_s: float, green_s: float, red_s: float, phase_offset_s: float = 0.0):
        if abs(green_s + red_s - cycle_length_s) > 1e-5:
            raise ValueError(f"green_s ({green_s}) + red_s ({red_s}) must equal cycle_length_s ({cycle_length_s})")
        self.cycle_length_s = cycle_length_s
        self.green_s = green_s
        self.red_s = red_s
        self.phase_offset_s = phase_offset_s

    def state_at(self, t_s: float) -> Literal["green", "red"]:
        # Adjust time by phase offset
        t_effective = (t_s - self.phase_offset_s) % self.cycle_length_s
        if t_effective < 0:
            t_effective += self.cycle_length_s
            
        if t_effective < self.green_s:
            return "green"
        else:
            return "red"
