# Test Scenarios

## `test_campus_multi_lane.json`

A hand-crafted, deterministic test scenario that exercises every major feature of the simulator in a single file. The network is a synthetic **campus loop** with three streets and three junctions:

- **Main Avenue** — a 4-lane (2 forward + 2 backward), curved street with a 6-point S-curve path (60 cells per lane), testing multi-lane geometry and lane-change dynamics.
- **Hostel Road** — a 2-lane (1 forward + 1 backward), straight street (40 cells per lane) forming the return leg of the loop.
- **Parking Access** — a 1-lane, one-way street (20 cells) branching off to a dead-end sink, testing open-road vehicle exit.

The scenario places **40 vehicles** deterministically (30 motorbikes, 10 cars) across all lanes with no overlaps, and includes **3 pre-placed disruptions**: a temporary breakdown on Main Avenue, a temporary 2-cell accident on Hostel Road, and a permanent parking reservation on Parking Access. A **batch schedule** triggers a flood blockage at step 100 and clears all temporary disruptions at step 300. Lane-changing is enabled (`lane_change_prob: 0.3`, `rear_safety_gap: 1`, `require_gain: true`) so the lateral transfer pass is active on the multi-lane streets.

### What this scenario tests

| Feature | How it's exercised |
|---|---|
| Multi-lane streets | Main Avenue has 4 lanes; Hostel Road has 2 |
| Curved geometry | Main Avenue's 6-point S-curve `path` on every lane |
| Lane changing | `lane_change_prob=0.3` with safety gap and gain requirement |
| Mixed vehicle types | 30 motorbikes (length 1) and 10 cars (length 2) |
| Junctions & turn routing | 3 junctions with weighted turn proportions summing to 1.0 |
| Temporary disruptions | Breakdown (1 cell, 50 steps) and accident (2 cells, 80 steps) |
| Permanent disruptions | Parking reservation on Parking Access |
| Scheduled events | Flood at step 100, clear-all at step 300 |
| Open roads & sinks | Parking Access exits to a dead end (no head junction) |
| Deterministic RNG | Seeded PCG64 state for exact reproducibility |

### Loading

- **WebSocket:** Send `{"type": "load_scenario", "data": <contents>}`.
- **Batch runner:** Include a `"batch"` key (already present) and submit via `run_scenario`.
- **Scenario Explorer:** Select the file from the UI file picker.

---

## `test_roundabout_interchange.json`

A hand-crafted scenario modelling a **4-way roundabout interchange** — every road is curved. A one-way clockwise ring of 4 arc-shaped segments (8 control points each) sits at the centre, with 4 two-lane approach streets (North, East, South, West) feeding in and out through curved S-bend paths (6 control points each).

The network has **12 roads**, **4 junctions** (one at each cardinal point of the ring), and **5 streets** (the ring + 4 approaches). The 4 approach inbound roads are open sources (`source_rate: 0.15`) so traffic flows in continuously, while the outbound roads are open sinks. This creates realistic merging/exiting pressure on the ring.

**47 vehicles** are pre-placed (32 motorbikes, 15 cars) across ring and approach roads. **4 pre-placed disruptions** include a breakdown on the NE ring, a 2-cell accident on the SW ring, a fallen tree on the north approach, and a permanent parking spot on the east exit.

The **batch schedule** has 4 events that unfold over 600 steps:

| Step | Event |
|------|-------|
| 80 | Trigger a flood disruption (randomly placed) |
| 200 | Increase lane-change aggressiveness (`prob=0.5`, no gain requirement) |
| 350 | Block 8 cells of the SE ring segment with a scheduled flood |
| 500 | Clear all temporary disruptions |

| Feature | How it's exercised |
|---|---|
| Curved geometry | All 12 roads have multi-point curved paths (arcs + S-bends) |
| Roundabout routing | 4 junctions with merge/exit turn proportions |
| Open sources & sinks | Approach inbound roads generate traffic; outbound roads drain it |
| Lane changing on ring | Ring segments grouped as a 4-lane street with `lane_change_prob=0.25` |
| Mixed vehicle types | 32 motorbikes (length 1), 15 cars (length 2) |
| Disruption variety | Breakdown, accident, fallen tree (temporary) + parking (permanent) |
| Scheduled parameter changes | Lane-change aggressiveness ramps up mid-run |
| Flood blockage | 8-cell ring blockage injected at step 350 |

### Loading

Same as above — WebSocket `load_scenario`, batch `run_scenario`, or the Scenario Explorer UI.

---

## `test_highway_corridor.json` (59 KB)

A **multi-lane highway corridor** with 3 interchanges. Three highway segments (3 lanes forward + 3 lanes backward each, 80 cells per lane) are connected by interchange junctions with on-ramps (sources) and off-ramps (sinks). A two-way service road provides an alternate route. All highway and ramp roads follow curved paths with 8+ control points.

- **26 roads** (18 highway lanes + 3 on-ramps + 3 off-ramps + 2 service road), **3 junctions**, **10 streets**
- **150 vehicles** (100 moto, 50 car), **5 disruptions** (breakdown, accident, tree, flood, parking)
- **8 scheduled events** over 1000 steps: flood trigger → rush hour source boost → aggressive lane changing → construction zone blockage → accident → cool-down → clear-all → conservative lane change

---

## `test_city_grid.json` (65 KB)

A **dense 3×3 city grid** — 4 horizontal and 4 vertical two-way streets forming 16 intersections. Each street has 3 segments of 20 cells between junctions (1 forward + 1 backward lane). Horizontal streets have gently curved paths (4 control points per segment); vertical streets are straight. Boundary roads have inflow sources and outflow sinks.

- **48 roads**, **16 junctions**, **8 streets**
- **200 vehicles** (140 moto, 60 car), **6 disruptions** (2 breakdowns, 2 accidents, 1 flood, 1 lock)
- **6 scheduled events** over 800 steps: breakdown trigger → rush-hour source rate → flood blockage → lane-change ramp → accident trigger → clear-all

---

## `test_star_network.json` (67 KB)

A **hub-and-spoke star network** with a central hexagonal ring and 6 radial spokes. The hex ring has 6 curved one-way segments (clockwise). Each spoke is a 4-lane two-way street (2 forward + 2 backward, 50 cells per lane) with sinusoidal curved paths. An outer ring of 6 curved segments connects the spoke endpoints. Every road in the network is curved.

- **36 roads** (6 hex ring + 24 spoke lanes + 6 outer ring), **12 junctions**, **18 streets**
- **180 vehicles** (120 moto, 60 car), **6 disruptions** (breakdown, accident, tree, flood, parking, lock)
- **7 scheduled events** over 1200 steps: flood → aggressive lane-change → hex flood blockage → accident → conservative lane-change → breakdown → clear-all

---

## Summary

| Scenario | Roads | Junctions | Streets | Vehicles | Curved Roads | Disruptions | Schedule | Size |
|---|---|---|---|---|---|---|---|---|
| Campus Multi-Lane | 8 | 3 | 3 | 40 | 6 | 3 | 2 events | 15 KB |
| Roundabout | 12 | 4 | 5 | 47 | 12 | 4 | 4 events | 22 KB |
| Highway Corridor | 26 | 3 | 10 | 150 | 24 | 5 | 8 events | 59 KB |
| City Grid | 48 | 16 | 8 | 200 | 24 | 6 | 6 events | 65 KB |
| Star Network | 36 | 12 | 18 | 180 | 36 | 6 | 7 events | 67 KB |
