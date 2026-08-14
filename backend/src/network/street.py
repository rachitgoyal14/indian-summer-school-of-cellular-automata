"""
street.py — streets and lane groups (Stage 9).

Stages 1–8 model a carriageway as a single `Road`: one 1D Rule 184 cell array.
Two-way traffic is two independent `Road`s joined at junctions. That is enough
for one lane per direction, but it cannot express *parallel* lanes running the
same way (R1‖R2, L1‖L2) because a `Road` has no notion of a sideways neighbour.

This module adds that notion without touching the CA itself:

  Lane    a `Road` plus its position in a lane group: `lane_index`, the
          `direction` it runs, and its `left_lane` / `right_lane` neighbours.
  Street  an ordered group of `Lane`s sharing one street id. A street may hold
          lanes in more than one direction (a two-way street); neighbours are
          only ever wired *within* a direction, since you cannot change lane
          into oncoming traffic.

Each lane's `Road` stays exactly what it was — a 1D Rule 184-compatible cell
array — so every existing simulation loop, serializer and metric keeps working
unchanged. `Street` is pure structure layered on top; it never steps anything.

Lane index convention
---------------------
Within a direction, `lane_index` increases from the *leftmost* lane to the
*rightmost* lane as seen by a driver travelling that direction. So:

    lane_index      0        1        2
                 [left] — [middle] — [right]       direction of travel →

    lanes[i].left_lane  is lanes[i - 1]   (None for the leftmost lane)
    lanes[i].right_lane is lanes[i + 1]   (None for the rightmost lane)

The two directions of one street are indexed independently: a two-way street
with two lanes each way has forward lanes 0,1 and backward lanes 0,1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from src.network.network import Road

FORWARD = "forward"
BACKWARD = "backward"

#: the directions a lane may run, relative to the street's own orientation,
#: in canonical order (all ordering in this module follows it, not alphabet).
DIRECTIONS: tuple[str, ...] = (FORWARD, BACKWARD)

_DIRECTION_RANK = {d: i for i, d in enumerate(DIRECTIONS)}


def _check_direction(direction: str) -> str:
    if direction not in _DIRECTION_RANK:
        raise ValueError(
            f"unknown lane direction {direction!r}; "
            f"expected one of {list(DIRECTIONS)}"
        )
    return direction


# `eq=False` gives lanes identity semantics: a lane is a node in a graph, and
# structural comparison would recurse forever through left/right neighbours.
@dataclass(eq=False)
class Lane:
    """One lane of a `Street`: a `Road` plus its place in the lane group."""

    road: Road
    lane_index: int = 0
    direction: str = FORWARD
    # `repr=False` for the same reason: neighbours form a cycle.
    left_lane: "Lane | None" = field(default=None, repr=False)
    right_lane: "Lane | None" = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _check_direction(self.direction)
        if self.lane_index < 0:
            raise ValueError(f"lane_index must be >= 0, got {self.lane_index}")

    # ------------------------------------------------------------ shortcuts
    @property
    def road_id(self) -> int:
        return self.road.id

    @property
    def length(self) -> int:
        return self.road.length

    @property
    def street_id(self) -> str | None:
        return self.road.street_id

    def neighbours(self) -> list["Lane"]:
        """Adjacent lanes in the same direction, left first. 0–2 entries."""
        return [n for n in (self.left_lane, self.right_lane) if n is not None]

    def is_leftmost(self) -> bool:
        return self.left_lane is None

    def is_rightmost(self) -> bool:
        return self.right_lane is None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Lane(road={self.road.id}, lane_index={self.lane_index}, "
            f"direction={self.direction!r})"
        )


class Street:
    """
    A named group of parallel lanes.

    Lanes are kept sorted by `(direction, lane_index)` and their left/right
    links are rewired on every mutation, so the group is always consistent.
    """

    def __init__(self, id: str, lanes: Iterable[Lane] = ()) -> None:
        self.id = str(id)
        self._lanes: list[Lane] = []
        for lane in lanes:
            self.add_lane(lane)

    # ------------------------------------------------------------- building
    @classmethod
    def from_roads(
        cls,
        id: str,
        roads: Iterable[Road],
        direction: str = FORWARD,
    ) -> "Street":
        """Build a one-direction street from roads, indexed left→right in order."""
        street = cls(id)
        for road in roads:
            street.add_road(road, direction=direction)
        return street

    def add_lane(self, lane: Lane) -> Lane:
        """Add an already-built `Lane`, stamping its road with this street's id."""
        _check_direction(lane.direction)
        for existing in self._lanes:
            if existing is lane or existing.road is lane.road:
                raise ValueError(
                    f"street {self.id!r}: road {lane.road.id} is already a lane"
                )
            if (existing.direction == lane.direction
                    and existing.lane_index == lane.lane_index):
                raise ValueError(
                    f"street {self.id!r}: duplicate lane_index {lane.lane_index} "
                    f"in direction {lane.direction!r}"
                )
        lane.road.street_id = self.id
        lane.road.lane_index = lane.lane_index
        self._lanes.append(lane)
        self._rewire()
        return lane

    def add_road(
        self,
        road: Road,
        direction: str = FORWARD,
        lane_index: int | None = None,
    ) -> Lane:
        """
        Wrap `road` in a new `Lane` and add it.

        With `lane_index=None` the road becomes the next lane to the right in
        that direction, which is the usual way to build a street left→right.
        """
        _check_direction(direction)
        if lane_index is None:
            lane_index = len(self.lanes_in_direction(direction))
        return self.add_lane(Lane(road=road, lane_index=lane_index, direction=direction))

    def remove_road(self, road_id: int) -> bool:
        """
        Drop the lane wrapping `road_id`, rewiring the neighbours it leaves.

        Lane indices of the survivors are left as they are: they are the
        street's own labelling, and renumbering them would silently move
        traffic between lanes. Adjacency is rebuilt, so the hole closes up.
        """
        for lane in self._lanes:
            if lane.road.id == road_id:
                self._lanes.remove(lane)
                lane.left_lane = lane.right_lane = None
                self._rewire()
                return True
        return False

    # ------------------------------------------------------------- querying
    def all_lanes(self) -> list[Lane]:
        """Every lane, ordered by direction then lane_index (left→right)."""
        return list(self._lanes)

    def lanes_in_direction(self, direction: str) -> list[Lane]:
        """The lanes running `direction`, ordered left→right."""
        _check_direction(direction)
        return [lane for lane in self._lanes if lane.direction == direction]

    def directions(self) -> list[str]:
        """The directions actually present, in canonical order."""
        seen = {lane.direction for lane in self._lanes}
        return [d for d in DIRECTIONS if d in seen]

    def roads(self) -> list[Road]:
        """Every lane's underlying `Road`, in lane order."""
        return [lane.road for lane in self._lanes]

    def lane_for_road(self, road_id: int) -> Lane | None:
        for lane in self._lanes:
            if lane.road.id == road_id:
                return lane
        return None

    def lane(self, lane_index: int, direction: str = FORWARD) -> Lane | None:
        for lane in self.lanes_in_direction(direction):
            if lane.lane_index == lane_index:
                return lane
        return None

    def is_two_way(self) -> bool:
        return len(self.directions()) > 1

    # ------------------------------------------------------------- protocol
    def __len__(self) -> int:
        return len(self._lanes)

    def __iter__(self) -> Iterator[Lane]:
        return iter(self._lanes)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Street(id={self.id!r}, lanes={len(self._lanes)})"

    # ------------------------------------------------------------- internal
    def _rewire(self) -> None:
        """Sort lanes and rebuild every left/right link from scratch."""
        self._lanes.sort(key=lambda l: (_DIRECTION_RANK[l.direction], l.lane_index))
        for direction in DIRECTIONS:
            group = [l for l in self._lanes if l.direction == direction]
            for i, lane in enumerate(group):
                lane.left_lane = group[i - 1] if i > 0 else None
                lane.right_lane = group[i + 1] if i + 1 < len(group) else None
