"""
cell_scale.py — real-world meters → cell-count conversion (Stage 8).

Decision and justification
--------------------------
A cell represents **7.5 meters** of road length. This value is chosen by
working backward from what makes typical campus/city roads produce reasonable
cell counts:

  - A typical campus internal road:  50–200 m  →  7–27 cells
  - A campus main avenue:            200–500 m →  27–67 cells
  - A city block segment:            100–300 m →  13–40 cells
  - A motorway on-ramp:              300–800 m →  40–107 cells

At 7.5 m/cell:
  - Short campus lanes (50 m) get ~7 cells — enough room for several vehicles
    and meaningful dynamics, not just a junction-to-junction hop.
  - Longer roads don't explode in cell count — a 500 m avenue is 67 cells,
    which is a comfortable amount for the engine.
  - A car (2 cells = 15 m) and a motorbike (1 cell = 7.5 m) have approximately
    realistic physical sizes (a real car is ~4.5 m; the oversize is because
    Rule 184 cells include the gap behind the vehicle, which is realistic —
    the safe following distance at ~30 km/h is several meters).

The value is a single constant here, easy to tune if field testing reveals a
better ratio.

Minimum road length
-------------------
Roads shorter than MIN_CELLS (3) after conversion are dropped — they are too
short for meaningful traffic dynamics (a single car already fills 2 of 3
cells). This is documented explicitly so the user knows very short real
segments are being elided.
"""

from __future__ import annotations

import math

# Meters per cell — the fundamental scale parameter.
METERS_PER_CELL = 7.5

# Roads shorter than this (in cells) are dropped.
MIN_CELLS = 3


def meters_to_cells(length_m: float) -> int:
    """
    Convert a real-world road length in meters to an integer cell count.

    Uses rounding (not truncation) so a 10 m road becomes 1 cell, not 0.
    Returns at least 1 so no zero-length road is ever created.
    """
    n = max(1, round(length_m / METERS_PER_CELL))
    return n


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distance in meters between two (lat, lon) points on the WGS84 ellipsoid,
    using the haversine formula (good to ~0.5% for short distances).
    """
    R = 6_371_000  # Earth mean radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
