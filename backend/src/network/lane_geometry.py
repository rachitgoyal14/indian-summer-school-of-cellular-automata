"""
lane_geometry.py — where a street's parallel lanes are drawn (Stage 11).

Lanes of one street share a baseline — the street's centreline — and are drawn
offset perpendicular to it so the renderer shows physically distinct tracks
instead of N identical overlapping lines.

This is purely a rendering concern. The offset moves a lane's `(x0, y0)`
origin and nothing else: cell count still comes from the real path length
divided by `METERS_PER_CELL`, and the physics never reads these coordinates.

Coordinate space
----------------
Both producers of network geometry put +y downward on screen — the OSM
projection negates latitude so north is up, and the procedural grid draws
rows downward. In that space, rotating a heading `(dx, dy)` to `(-dy, dx)`
points to the driver's **right**:

    heading east (1, 0) → (0, 1) → +y → downward on screen → south → right ✓

so `perpendicular_right` is the signed axis every offset here is measured on.

Slot layout
-----------
A street's lanes occupy `n_slots` evenly spaced slots across its width,
centred on the baseline. Slot 0 is the leftmost as the *forward* driver sees
it, slot `n_slots - 1` the rightmost:

        slot 0      slot 1      slot 2
      ────────────────────────────────────  → forward travel
        left       centre       right

For a two-way street the two directions share that width. India drives on the
left, so looking along the forward direction the forward lanes take the left
half and the oncoming lanes the right half. The backward lanes are laid out
mirrored, since their own driver's "leftmost" is the far side of the road:

    forward lanes   f0 f1 ... f(F-1)  |  b(B-1) ... b1 b0   backward lanes
                    <- forward driver's left ... right ->

`street_slot` computes that index, so both directions of a street tile the
width without overlapping. Set `drive_side="right"` for right-hand traffic,
which simply swaps the two halves.
"""

from __future__ import annotations

import math

from src.mapdata.cell_scale import METERS_PER_CELL

#: width of one lane, in metres. Real Indian urban lanes are ~3.0–3.5 m.
LANE_WIDTH_M = 3.5

#: the same width expressed in cell-lengths, for builders whose coordinates
#: are in cells rather than metres (the procedural grid).
LANE_WIDTH_CELLS = LANE_WIDTH_M / METERS_PER_CELL

#: which side of the road traffic keeps to. IIT (BHU) is in India: left.
DRIVE_SIDE = "left"


def perpendicular_right(dx: float, dy: float) -> tuple[float, float]:
    """
    Unit vector 90° to the right of the heading `(dx, dy)`.

    Returns `(0.0, 0.0)` for a degenerate heading so callers can offset by it
    harmlessly rather than dividing by zero.
    """
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return 0.0, 0.0
    return -dy / length, dx / length


def slot_offset(slot: int, n_slots: int, lane_width: float) -> float:
    """
    Signed distance from the centreline to a slot, positive to the right.

    Slots are centred on the baseline, so a 1-slot street sits exactly on it
    and a 2-slot street straddles it by half a lane width either way.
    """
    if n_slots <= 0:
        return 0.0
    return (slot - (n_slots - 1) / 2.0) * lane_width


def street_slot(
    lane_index: int,
    direction: str,
    n_forward: int,
    n_backward: int,
    drive_side: str = DRIVE_SIDE,
) -> int:
    """
    The across-the-width slot for one lane of a (possibly two-way) street.

    `lane_index` is the lane's index within its own direction, counted from
    that direction's driver's left. The result is counted from the *forward*
    driver's left, so both directions share one consistent ruler.
    """
    forward_first = drive_side == "left"
    if direction == "forward":
        return lane_index if forward_first else n_backward + lane_index
    # a backward lane's own leftmost is the far edge of the road
    mirrored = n_backward - 1 - lane_index
    return (n_forward + mirrored) if forward_first else mirrored


def offset_origin(
    x0: float,
    y0: float,
    dx: float,
    dy: float,
    slot: int,
    n_slots: int,
    lane_width: float,
) -> tuple[float, float]:
    """
    Shift a lane's origin sideways onto its slot.

    `(dx, dy)` is the lane's per-cell step, which fixes the heading; only the
    origin moves, so the lane stays parallel to the baseline and keeps its
    length in cells.
    """
    px, py = perpendicular_right(dx, dy)
    off = slot_offset(slot, n_slots, lane_width)
    return x0 + px * off, y0 + py * off
