# PHASE 3 — Multi-Lane and Junction Configurations

## Before you start
Read `plan.md` in full, especially Section 7 risk #2 (junction logic is not "pure" Rule 184 — that's expected and fine). Requires Phase 2's rendering working on top of Phase 1's validated engine.

## Goal of this phase
Implement the brief's 5 listed lane/junction configurations, building up from the single lane already working:
1. Original, one-way (already done — Phase 1/2).
2. Two-way, no interaction.
3. Two-way, with left/right turns.
4. Two-way, both directions with left/right turns.
5. Connected multi-junction network.

## Steps

### 1. `src/core/junction.py`
- A `Junction` represents a cell shared by 2+ roads (an intersection point in the network).
- `Junction` has a mapping of incoming roads to outgoing roads with turn proportions (e.g. from Road A, 70% continue to Road B (straight), 15% to Road C (left), 15% to Road D (right) — proportions configurable, must sum to 1.0 per incoming road, raise `ValueError` if not).
- `decide_exit_road(incoming_road_id, turn_proportions, rng) -> outgoing_road_id`: weighted random choice. Write `tests/test_junction.py`: proportions sum-validation, and a statistical test that over many draws with a fixed seed, observed frequencies are within a reasonable tolerance of configured proportions.
- When a car reaches a junction cell (its road's last cell) and the chosen outgoing road's first cell is empty, it moves there (following Rule 184's same "move if empty" logic, just crossing from one road's array to another's); otherwise it waits, exactly as Rule 184 already handles a blocked forward cell.

### 2. Case 2 — Two-way, no interaction
Two independent one-way `Road` arrays (already built in Phase 1) running in opposite directions, rendered side by side or overlapping visually but with completely independent state — no shared cells, no interaction. This is the simplest possible extension; mostly a rendering/configuration exercise, not new core logic.

### 3. Case 3 — Two-way, with turns
One junction connecting a two-way road pair to at least one cross-street, using the `Junction` class from step 1. Cars traveling on the main road, upon reaching the junction, either continue straight or turn onto the cross-street per configured proportions.

### 4. Case 4 — Two-way, both directions with turns
Extend case 3 to a full 4-way intersection: both directions on both the main road and the cross-street, all meeting at one junction, with turn proportions configured for each of the 4 incoming directions independently.

### 5. Case 5 — Connected multi-junction network
Multiple case-4 intersections linked together (e.g. a 3x3 grid of junctions connected by road segments), so a car can travel through several junctions in sequence and congestion/disruption at one junction can propagate to affect traffic approaching neighboring junctions.
- `src/network/grid_builder.py`: `build_grid_network(rows: int, cols: int, segment_length_cells: int) -> Network`: constructs a rectangular grid of connected junctions with road segments of configurable length between them. This is the "campus/town" network the brief describes, built proceduraly rather than from real map data (documented as a deliberate simplification in `PHASE_REPORT.md`, consistent with plan.md Section 2's assumption).

### 6. Update `src/render/pygame_view.py`
- Extend rendering to draw multiple connected roads and junctions in a 2D layout (not just one horizontal strip) — junctions as distinct visual markers, roads as connected line segments of cells.
- Confirm zoom/pan (from Phase 2) still works correctly over a full multi-junction network, not just a single lane.

## Validation
- `tests/test_junction.py` passing (turn-proportion validation and statistical distribution check).
- A dedicated test confirming **no two cars ever occupy the same cell** across a junction transition (a car moving from one road onto another must respect the same "only move if target cell is empty" rule as within a single road — write `tests/test_no_junction_collision.py` running a multi-junction network for many steps and asserting zero collisions).
- Manually run the case-5 connected network in the Pygame viewer and confirm: cars visibly travel across multiple junctions in sequence, turning behavior looks reasonable (not all cars going the same direction unless configured that way), and congestion introduced at one junction (e.g. by manually setting a very high density) visibly backs up traffic approaching that junction from neighboring roads.

## Acceptance criteria
- [ ] `pytest -q` passes — Phase 1/2 regression tests plus new junction and collision tests.
- [ ] All 5 lane/junction configurations implemented and manually confirmed working in the Pygame viewer.
- [ ] Zero collisions confirmed via `test_no_junction_collision.py` over an extended run.
- [ ] `PHASE_REPORT.md` updated with a `## Phase 3` section, including which configuration cases were tested and how, and confirmation of the grid-network-instead-of-real-map-data simplification.
- [ ] Git commit made.

## Explicitly out of scope
No disruption events yet (Phase 4), no analytics beyond basic flow/density (Phase 5), no map editing or save/load (Phase 6).
