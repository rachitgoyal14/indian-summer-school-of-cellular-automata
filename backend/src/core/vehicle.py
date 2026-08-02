"""
vehicle.py — heterogeneous vehicle footprints (Stage 3).

Stage 1/2 treated the road as a binary 0/1 array (every vehicle = 1 cell).
Stage 3 introduces vehicles that occupy a configurable number of *consecutive*
cells:

    motorbike : 1 cell
    car       : 2 cells   (see FOOTPRINTS / justification below)

Design
------
We move to an *agent* representation: each `Vehicle` knows its `front` cell
(the leading cell, i.e. the highest index in its travel direction), its
`length` (footprint), and its `vtype`. A road's occupancy array is *derived*
from the vehicle list, so there is a single source of truth (the vehicles)
and no chance of the occupancy grid and the vehicle list drifting apart.

Why car = 2 cells (not 3):
- The brief only needs a clear, visible size distinction between the two
  vehicle classes; 2:1 is the minimal footprint ratio that renders as an
  obviously longer vehicle.
- Larger footprints reduce a lane's carrying capacity super-linearly and
  push the dynamics further from the exactly-solvable Rule 184 baseline; 2
  keeps single-motorbike lanes numerically identical to classic Rule 184
  (the Stage 1 regression target) while still delivering the visual/spatial
  distinction the brief asks for.
- The value is a single constant here, so bumping cars to 3 later is a
  one-line change if desired.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical footprints, in cells.
FOOTPRINTS: dict[str, int] = {
    "moto": 1,
    "car": 2,
}


@dataclass
class Vehicle:
    """
    A vehicle on a single road.

    `front` is the index of the leading cell (largest index in the +index
    travel direction). The body trails behind, so the vehicle occupies the
    `length` cells ending at `front`:  [front-length+1 .. front].
    """

    id: int
    front: int
    length: int
    vtype: str

    def cells(self, road_length: int, periodic: bool) -> list[int]:
        """Return the list of cell indices this vehicle occupies."""
        idxs = [self.front - k for k in range(self.length)]
        if periodic:
            return [i % road_length for i in idxs]
        # open road: clip anything that has run off the tail end (< 0)
        return [i for i in idxs if 0 <= i < road_length]

    @property
    def tail(self) -> int:
        """Index of the trailing cell (may be negative before wrapping)."""
        return self.front - self.length + 1
