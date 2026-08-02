# stages.md — Execution Plan for Real Map Import + Visual Realism Upgrade

Continues directly from the existing Stage 1-6 build (do not touch or re-verify those unless a regression is found). These are numbered Stage 8 and Stage 9 to make clear they follow the already-completed Stage 7 polish pass in the existing PHASE_REPORT.md.

**Do not skip Stage 8's correctness verification to get to the visual work faster** — a real map that's been mistranslated (wrong junction connectivity, wrong one-way directions, broken cell footprints) will produce a simulator that *looks* real but behaves nonsensically, which is worse than a synthetic grid that's honest about not being real. Get the translation right and proven first.

---

## Stage 8 — Dynamic Real-World Map Import

**Read `plan.md` Sections 2, 3, and 5 first.**

### 8a. Region lookup
Build (`backend/src/mapdata/`):
- `geocode.py`: given a place name (e.g. "IIT BHU Varanasi"), query Nominatim (OSM's free geocoding service) and return a bounding box (lat/lon corners). Handle the case where the search returns multiple/ambiguous results — pick the first reasonable match and log what was chosen, don't silently guess.
- `overpass_client.py`: given a bounding box, query the Overpass API for all roads (`highway=*` ways) within it, returning the raw OSM graph (nodes with lat/lon, ways connecting them, tags including name and one-way flags). Handle and clearly report API failures/timeouts (Overpass has rate limits and occasional downtime) — this must not crash the whole import, it should fail with a clear, user-visible message.

### 8b. The core translation: OSM graph -> simulator Network
Build:
- `osm_to_network.py`: the actual translation logic. This is the hard part — work through it carefully:
  1. Identify junction nodes: any OSM node where 3+ road ways meet, or where a way's tags change (e.g. a name change), becomes a `Junction`.
  2. Between consecutive junction nodes along a way, the road segment becomes a `Road` — compute its real-world length (haversine distance along the node chain) and convert to a cell count per `cell_scale.py`'s decision (see 8c).
  3. Respect one-way tags: OSM `oneway=yes` roads become single-direction `Road`s; two-way roads become a `Road` pair (or your existing two-way representation from the procedural builder, whichever the engine already expects — reuse it, don't invent a new one).
  4. At each `Junction`, initialize turn proportions as an even split across all valid outgoing directions (a clearly labeled default, not a measured value — document this explicitly).
  5. Curved ways (more than 2 nodes between junctions) are simplified into a single straight-line `Road` of the same total path length (per plan.md Section 3's stated geometric simplification) — do not attempt to render true curves in this stage.
- `cell_scale.py`: `meters_to_cells(length_m: float) -> int`, with the actual conversion ratio decided and justified here — run a few real examples (e.g. a typical campus road segment might be 50-200m; decide what cell size makes that produce a reasonable, simulatable cell count, neither too coarse nor absurdly fine) and document the reasoning, not just a magic number.

### 8c. Validation — this is the acceptance bar, not optional
- `tests/test_osm_to_network.py`: using a small, hand-constructed synthetic OSM-format fixture (a tiny 3-4 road, 2-3 junction graph you build by hand, not a real API call — so this test doesn't depend on network access), assert the translation produces the correct number of roads and junctions, correct connectivity, and correct one-way handling.
- `tests/test_cell_scale.py`: assert the meters-to-cells conversion is monotonic and produces sane results across a range of realistic road lengths (very short campus paths through longer city roads).
- **Real-data smoke test:** run the full pipeline (geocode -> Overpass -> translate) against IIT (BHU) Varanasi's actual coordinates. Report, concretely: how many roads and junctions were extracted, whether the resulting network's shape is visibly recognizable as the campus when plotted (even just as a rough matplotlib line plot of road positions, before any frontend work), and whether the simulation actually runs on it without errors (vehicles moving, no crashes) for at least a few hundred steps.
- **Regression check, explicitly required:** run the exact same flow-density and no-collision checks used for the procedural grid network (from the earlier stages) against the newly-imported real network. If a real network at a comparable density produces meaningfully different flow/collision behavior than a procedural one, that's a sign the translation introduced a structural bug (e.g. a broken junction, a cell-footprint mismatch) — investigate and fix before proceeding, don't attribute a discrepancy to "real data is just different" without checking.

### Frontend (minimal for this stage — full visual work is Stage 9)
- `components/RegionSearch.tsx`: a simple text input + search button that sends a region-import request to the backend and loads the result via the existing network-replacement mechanism (reuse Stage 6's `load_scenario`-style flow if it fits, or add a parallel `import_region` message — decide and document which).
- No new rendering work required yet — the existing renderer should already be able to display the imported network, since it's structurally the same `Network` type as always. If it can't (e.g. it assumes a simple grid layout), that's a bug in the existing renderer to fix now, not defer.

Acceptance criteria:
- [ ] `pytest -q` passes — all prior regression tests plus new OSM-translation and cell-scale tests.
- [ ] Real-data smoke test against IIT (BHU) Varanasi completed and reported with concrete numbers (roads, junctions, step count run, any errors).
- [ ] The imported network's shape is visibly recognizable as the real campus layout (attach the rough position plot).
- [ ] Regression check against procedural-grid flow/collision behavior passes, or any discrepancy is investigated and explained, not hand-waved.
- [ ] Region search UI works end-to-end: type a place name, get a real network loaded and running.
- [ ] `PHASE_REPORT.md` updated with a `## Stage 8` section, including the cell-scale decision and its justification, the one-way/curve-simplification handling, and the smoke-test results.
- [ ] Git commit made.

**Also attempt IIEST Shibpur as a second real test case** and report whether it worked equally well or surfaced new edge cases (e.g. different road-tagging conventions in that area's OSM data) — two real regions is a much stronger "this generalizes" claim than one.

---

## Stage 9 — Visual Realism Upgrade (2D)

**Read `plan.md` Sections 3 (visual design decision) and 4 (what "realism" concretely means) first. This is a redesign of the existing rendering, not a new system — do not touch simulation logic, WebSocket messages, or backend code except where a real data field (e.g. road name) needs to be added to the schema for the frontend to use.**

### 9a. Road rendering
- Rework `RoadRenderer.ts`'s road drawing: replace flat colored rectangles with a road-surface look — a base asphalt tone, a subtle centerline or edge marking, rounded/mitered joins at junctions rather than hard rectangle overlaps.
- If road names are available (from Stage 8's OSM import), render them as labels along the road at appropriate zoom levels (fade in as you zoom in, hide when zoomed out and the label would overlap others — a simple distance/zoom-based visibility rule is enough, not a full label-collision-avoidance system).

### 9b. Vehicle rendering
- Replace flat rectangles with simple but recognizable vehicle shapes (a small rounded rectangle with a directional "front" indicator is enough — this doesn't need to be photorealistic, just recognizable as "a car" or "a motorbike" rather than "a colored block"), correctly rotated to face the direction of travel.
- Keep the existing motorbike/car size and color distinction from Stage 3/Stage 7 — this upgrade is about shape and orientation, not re-deciding color semantics that already work.

### 9c. Camera and motion feel
- Add eased (smoothly interpolated) zoom and pan transitions instead of instant jumps — when the user scrolls to zoom or the view recenters, it should glide rather than snap.
- Confirm this doesn't reintroduce any of the desync issues Stage 2 specifically tested for (the debug visible-cell-range readout should still always match what's rendered, even mid-transition) — add a check for this specifically, since easing/interpolation is a common place for a rendering-vs-data mismatch to sneak in.

### 9d. Disruptions and heatmap presentation
- Redesign disruption markers to read as map annotations/icons (e.g. a small distinct icon or marker per disruption type) rather than flat color-filled cells, while preserving the existing color-coding logic underneath (per Stage 4/7's semantic color choices — don't relitigate which color means what, just how it's drawn).
- Keep the heatmap's existing green-to-red logic and layering priority (Stage 5/7) but reconsider its visual treatment so it reads as a traffic-density overlay (like a live traffic layer in a mapping app) rather than a flat debug tint.

### Validation
- Manual, side-by-side comparison: screenshot the SAME scenario (same region, same step, same zoom) before and after this stage's changes, and describe concretely what changed and why it reads as more "natural" — this is a subjective area, so the burden is on a clear, specific before/after comparison, not just an assertion that it looks better.
- Confirm no functional regression: all existing interactions (map editor clicks, disruption toggles, zoom/pan, save/load) still work exactly as before — this stage should be visually transformative but functionally invisible in terms of what still works.
- Performance check: confirm the added visual detail (road textures, vehicle shapes, eased camera) doesn't introduce visible frame stutter, especially on the larger real-world networks from Stage 8 — profile and report actual frame timing, the same standard used in the original Stage 7 polish pass.

Acceptance criteria:
- [ ] `pytest -q` passes — no backend regressions (this stage should touch backend only minimally, if at all).
- [ ] Before/after screenshots attached with a specific description of what changed.
- [ ] Road, vehicle, camera-motion, and disruption/heatmap treatments all match Section 4's 5 points, confirmed one at a time.
- [ ] Desync check confirms eased camera motion never causes the visible-cell-range readout to disagree with what's rendered.
- [ ] All existing interactions confirmed still functionally correct (no regression in map editor, disruptions, save/load, etc.).
- [ ] Frame-timing performance confirmed acceptable on at least one Stage 8 real-world network, not just the small synthetic test cases.
- [ ] `PHASE_REPORT.md` updated with a `## Stage 9` section.
- [ ] Git commit made.

---

## After Stage 9

This is a natural point to demo the campus-specific version live to Dr. Das and Prof. Martinez — ideally loading IIT (BHU) or IIEST Shibpur by name in front of them, rather than a pre-loaded scenario, since "type the name of any place and it works" is the actual capability being delivered. Worth testing that exact live-search flow once beforehand on the demo machine, including with a real internet connection (Overpass/Nominatim both require live network access, which is a new dependency this project didn't have before — confirm the demo environment has it).

3D rendering (Three.js) remains explicitly deferred per plan.md Section 7 — only worth revisiting as its own separate, scoped decision after this 2D version has actually been shown and evaluated, not assumed necessary in advance.