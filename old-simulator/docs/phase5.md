# PHASE 5 — Live Analytics (Density, Entropy, Log Plots, Heatmap)

## Before you start
Read `plan.md` in full. Requires Phase 4's disruption system working with confirmed-unperturbed baseline flow-density behavior.

## Goal of this phase
Add live-updating analytics alongside the running simulation: density over time, Shannon entropy, log-scale plots, and a spatial heatmap of congestion across the network.

## Steps

### 1. `src/analytics/density.py` (extend from Phase 1's minimal version)
- `network_density(network_state) -> float`: aggregate density across all roads in a multi-road network (not just a single lane anymore).
- `per_road_density(network_state) -> dict[road_id, float]`: density broken out per road segment, needed for the heatmap.

### 2. `src/analytics/entropy.py`
- `shannon_entropy(state: np.ndarray, window_size: int) -> float`: divide the road (or network) into fixed-size windows, compute the fraction of occupied cells in each window, treat this as a probability distribution across windows, and compute Shannon entropy: `-sum(p_i * log2(p_i))` for each non-zero `p_i`. Write `tests/test_entropy.py` with hand-computable fixtures: e.g. a state where cars are evenly spread across all windows (high entropy, close to the theoretical maximum for that window count) vs. a state where all cars are clustered in one window (low entropy, near zero) — assert your function distinguishes these correctly and give the actual expected numeric range for each case.
- Document clearly in code comments and `PHASE_REPORT.md` why entropy is a useful complementary measure to density: two networks can have identical average density but very different entropy — one smoothly distributed (higher entropy, likely free-flowing), one heavily clustered into jams in a few spots (lower entropy, likely congested) — this is exactly the kind of distinction density alone can't make.

### 3. `src/analytics/heatmap.py`
- `road_congestion_heatmap(network_state, per_road_density) -> renderable_overlay`: a color-coded overlay (e.g. green=low density, red=high density) applied to each road segment's rendering in the Pygame view, updated live.

### 4. Log-scale plots
- Add a live-updating matplotlib (or Pygame-native) plot window showing density and flow over time on a log scale, useful for visualizing behavior across a wide range of values (e.g. very sparse and very jammed regimes on the same readable plot) — can be a separate window/panel from the main Pygame simulation view if that's simpler to implement well.

### 5. Update `src/render/pygame_view.py`
- Integrate the heatmap overlay onto road rendering (toggleable on/off, since it may visually compete with the disruption-type coloring from Phase 4 — decide and document a sensible priority, e.g. heatmap as a background tint with disruption markers drawn on top).
- Add a live readout panel showing current network-wide density, entropy, and flow numbers, updating each step or every few steps.

## Validation
- `tests/test_entropy.py` passing with the hand-computed fixtures.
- Manually run the simulator across a range of densities and disruption scenarios and confirm in `PHASE_REPORT.md`: does entropy behave as expected (drops visibly when a disruption creates a localized jam, even if overall network density doesn't change much)? Does the heatmap visibly highlight the same congested regions you can also see directly in the main simulation view (cross-check the two against each other — if the heatmap shows a region as low-congestion while you can visually see a queue backed up there in the main view, that's a bug in the heatmap calculation, not a valid finding)?

## Acceptance criteria
- [ ] `pytest -q` passes — all regression tests plus new entropy tests.
- [ ] Live density, entropy, log-scale, and heatmap displays all working and updating during a running simulation.
- [ ] Heatmap cross-checked against visible congestion in the main view and confirmed consistent.
- [ ] `PHASE_REPORT.md` updated with a `## Phase 5` section describing the entropy-vs-density behavior observed across at least 2-3 different disruption scenarios.
- [ ] Git commit made.

## Explicitly out of scope
No landscape classification, map editing, or save/load yet — those are Phase 6.
