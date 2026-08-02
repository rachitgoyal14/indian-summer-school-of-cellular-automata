# plan.md — Real-World Map Import + Visual Realism Upgrade

**Builds on:** the existing, working simulator (Stages 1-6 complete: Rule 184 engine, WebSocket + React/PixiJS frontend, 5 lane/junction configurations, 8 disruptions, live analytics, map editor, save/load). This document does **not** replace any of that — it adds two new, mostly-independent capabilities on top of it.

**Why this now:** at the last meeting, Dr. Das confirmed the missing piece is a **real campus network** — a procedurally generated grid proves the physics works, but doesn't let anyone actually reason about "what happens if we close this road," because it isn't a road anyone recognizes. This directly serves the brief's stated objective: *"help to take decisions to plan, reorganize, redesign, and collapse avenues."* A synthetic grid cannot do that; a real, recognizable layout can.

---

## 1. What's in scope, and what's explicitly deferred (confirmed with you directly)

| Item | Status |
|---|---|
| Dynamic import of a real road network for **any given region**, via live map data (not a fixed campus baked into the code) | **In scope** |
| First real test case: **IIT (BHU) Varanasi and/or IIEST Shibpur** | **In scope** |
| File upload of a map (GeoJSON/OSM export, or a scanned/photographed map) | **Deferred** — explicitly parked, not part of this plan |
| A genuine 2D visual realism upgrade (the "feels synthetic" problem) | **In scope** |
| Switching the renderer to 3D (Three.js) | **Deferred** — treated as a possible future decision only after this 2D upgrade is evaluated, not committed to now |

This deferral is worth restating plainly to Dr. Das and Prof. Martinez when this is shown: it's a deliberate sequencing choice (get the real-map feature and a genuinely better-looking 2D version working and solid first), not an oversight.

---

## 2. Where real road data comes from

**OpenStreetMap (OSM)**, via its free, public **Overpass API**. This is the standard, well-documented source for exactly this kind of data — road centerlines, intersections, one-way flags, road names — for anywhere on Earth that's been mapped, which includes essentially all Indian university campuses and cities in reasonable detail.

Concretely: a user (or the system, given a place name / coordinates / bounding box) sends a query to Overpass, gets back raw geographic road data (a graph of points and the road segments connecting them), and that raw data needs to be turned into something the existing Rule 184 engine can run — a set of `Road` objects (cell arrays) connected by `Junction` objects, in exactly the same internal format the procedural grid builder already produces. **This conversion step — not the data-fetching — is the real engineering work in this plan**, because real-world roads are geometrically messy in ways a synthetic grid never is: curved roads, junctions with 3, 5, or more connecting roads, wildly different segment lengths, one-way streets, roads that nearly-but-not-quite intersect.

---

## 3. Core design decisions

- **The existing simulation engine does not change.** `rule184.py`, `footprint.py`, `network.py`, `disruptions.py`, the analytics, all of it stays exactly as-is. A real-world network is just a different *input* to the same `Network` object the procedural grid builder already produces — this plan only adds a new way to construct that input, not a new way to simulate it. This is the single most important design constraint: if simulation behavior differs between a procedural grid and a real map at the same density, that's a bug, not a feature of "real" data.
- **Geometric simplification, stated explicitly, not hidden.** Real roads will be simplified into straight-line segments between junctions (matching the existing `Road` model's geometry, which is already a straight-line segment per road). Curved real roads become a sequence of shorter straight segments joined at synthetic junctions where needed. This is a deliberate, documented approximation — pursuing true curved-road rendering is out of scope here and would be a much larger undertaking for limited payoff at this stage.
- **Cell size vs. real-world scale — a real decision, not an afterthought.** The existing engine's cell size (from earlier stages) was chosen for a synthetic grid at a convenient scale. Real roads have real lengths in meters, which need to map to a sensible number of cells — too coarse and short campus roads become 2-3 cells (junctions dominate, no room for real traffic dynamics); too fine and a large region becomes computationally heavy. This must be explicitly decided and justified in Stage 8 (below), not left as a default.
- **Junction turn proportions for a real network default to sensible, clearly-labeled placeholders** (e.g. even split among available directions), editable afterward through the existing Stage 6 map editor's turn-proportion controls — OSM data doesn't reliably include real observed turning behavior, so this is honest about being a starting default, not a measured value.
- **Region selection UI:** a simple search-by-place-name box (geocoded to a bounding box via a free geocoding service, e.g. Nominatim, which pairs naturally with OSM/Overpass) plus a manual bounding-box override for precision — this avoids needing a full interactive draw-a-box-on-a-live-map control as a first version, which is a reasonable simplification to state explicitly.
- **Visual realism upgrade stays within the current PixiJS/2D architecture.** No renderer replacement. The goal is treating the existing 2D canvas the way a well-designed map application would (think a traffic-layer view in a mapping app, or a city-builder game's top-down view) rather than flat colored rectangles on a dark background — real road-surface texturing, lane markings, a legible basemap-like feel, better vehicle sprites, smoother camera motion.

---

## 4. What the visual realism upgrade specifically means

The current interface's core complaint was "feels synthetic" — this needs a concrete definition to actually fix, not just "make it prettier":

1. **Roads should read as roads**, not as generic colored bars — asphalt-toned surfaces, subtle lane-marking details, road edges that look intentional.
2. **The map should feel like a map** — when a real campus is loaded, it should be recognizable as that campus's actual layout at a glance, with road names visible at appropriate zoom levels (OSM data includes names — use them).
3. **Vehicles should read as vehicles**, not as colored dots — simple but recognizable car/motorbike silhouettes rather than plain rectangles, oriented correctly along their direction of travel.
4. **Camera motion should feel deliberate** — smooth eased zoom/pan rather than instant jumps, consistent with how real map applications behave.
5. **Disruptions and the heatmap should feel like map annotations**, not debug overlays — e.g. an accident should read visually like an incident marker, not just a red-tinted cell block.

This is a genuine design pass, not a palette swap — treat it with the same seriousness as the earlier Stage 7 polish pass, but scoped specifically around "does this look like a real mapping/simulation tool" rather than general tidiness.

---

## 5. Suggested repo additions

```
backend/
  src/
    mapdata/
      overpass_client.py       <- queries the Overpass API for a bounding box
      geocode.py                 <- place-name -> bounding box (Nominatim)
      osm_to_network.py            <- the core translation: raw OSM graph -> Road/Junction objects
      cell_scale.py                  <- real-world meters -> cell-count decision, documented
  tests/
    test_osm_to_network.py
    test_cell_scale.py
frontend/
  src/
    components/
      RegionSearch.tsx          <- place-name search + bounding-box override UI
    render/
      (existing RoadRenderer.ts substantially reworked per Stage 9 below,
       not a new file — this is a redesign of what's there)
docs/
  evidence/
    stage8/
    stage9/
```

---

## 6. Deliverables checklist

- [ ] Stage 8: real road network import for a given region (IIT BHU and/or IIEST Shibpur as the first real test case), producing a `Network` object indistinguishable in structure from a procedurally-built one, running correctly in the existing engine with zero simulation-logic changes.
- [ ] Stage 9: visual realism upgrade — roads, vehicles, camera motion, and disruption/heatmap presentation all redesigned per Section 4, still within the existing 2D PixiJS architecture.

---

## 7. Explicitly deferred, for the record

- Map file upload (GeoJSON/OSM file, or scanned/photographed map) — parked, not part of this plan.
- 3D rendering (Three.js) — parked as a future, separate decision, to be reconsidered only after Stage 9's 2D result has actually been seen and evaluated, not committed to now.