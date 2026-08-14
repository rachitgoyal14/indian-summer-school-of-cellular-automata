"""
osm_to_network.py — translate raw OSM graph data into a simulator Network.

This is the core of Stage 8: the module that takes the raw nodes-and-ways
graph from the Overpass API and produces a Network object (roads + junctions)
in exactly the same format the procedural grid builder produces. The
simulation engine does not change — a real-world network is just a new kind
of input.

Translation algorithm
---------------------
1. **Identify junction nodes**: any OSM node where 3+ way endpoints or
   internal route points meet. Also, way endpoints are always potential
   junctions if shared between ways.

2. **Split ways at junctions**: each way is split into segments between
   consecutive junction nodes. Each segment becomes a Road.

3. **Compute road lengths**: haversine distance along the node chain
   between junctions, converted to cells via cell_scale.

4. **Respect one-way**: OSM `oneway=yes` → single-direction Road; otherwise
   two Roads (one per direction) are created between the same junctions.

5. **Junction turn proportions**: initialized as even split across all
   valid outgoing directions (a clearly labeled default, not a measured
   value — documented explicitly per newPlan.md §3).

6. **Geometry**: roads get (x0, y0, dx, dy) in a projected coordinate
   space (simple equirectangular projection from lat/lon → meters, then
   normalized for display). This preserves the recognizable real-world
   shape of the network.

Curve simplification (per newPlan.md §3)
-----------------------------------------
Curved ways (more than 2 nodes between junctions) are simplified into a
single straight-line Road whose cell count equals the total path length
(haversine along all intermediate nodes). The road's geometry (x0, y0, dx,
dy) goes from the start junction to the end junction in a straight line.
This is the documented approximation.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from src.core.junction import Junction
from src.network.network import Network, Road
from src.network.lane_geometry import (
    LANE_WIDTH_M,
    offset_origin,
    street_slot,
)
from src.network.street import BACKWARD, FORWARD, Street
from src.mapdata.cell_scale import meters_to_cells, haversine, MIN_CELLS

logger = logging.getLogger(__name__)

ONEWAY_TRUE = ("yes", "1", "true", "-1")


def parse_lanes(tags: dict[str, Any]) -> tuple[int, int, str]:
    """
    Read `lanes=*` / `oneway=*` into (forward lanes, backward lanes, why).

    OSM lane tagging is inconsistent. v1 handles the plain `lanes=*` tag only;
    anything missing or malformed falls back to one lane per direction, which
    is exactly the pre-Stage-11 behaviour. The third return value explains the
    choice so an import can be debugged from the log.

      oneway=yes, lanes=2   → 2 forward, 0 backward
      oneway=no,  lanes=2   → 1 forward, 1 backward
      oneway=no,  lanes=4   → 2 forward, 2 backward
      oneway=no,  lanes=3   → 2 forward, 1 backward  (odd: extra lane forward)
      no lanes tag          → 1 per direction
    """
    oneway = str(tags.get("oneway", "no")).strip().lower() in ONEWAY_TRUE

    raw = tags.get("lanes")
    total: int | None = None
    if raw is not None:
        try:
            total = int(str(raw).strip())
        except (TypeError, ValueError):
            total = None
        if total is not None and total < 1:
            total = None

    if total is None:
        why = "no usable lanes tag" if raw is None else f"malformed lanes={raw!r}"
        return (1, 0, why) if oneway else (1, 1, why)

    if oneway:
        return total, 0, f"oneway with lanes={total}"
    if total == 1:
        # a two-way street still needs a lane each way, whatever the tag says
        return 1, 1, "two-way but lanes=1; one lane each way"
    forward = (total + 1) // 2
    return forward, total - forward, f"two-way with lanes={total}"


def osm_to_network(
    osm_data: dict[str, Any],
    source_rate: float = 0.3,
    car_fraction: float = 0.3,
) -> Network:
    """
    Convert raw OSM data (from overpass_client.fetch_roads) into a Network.

    Parameters
    ----------
    osm_data : dict with "nodes" and "ways" as returned by fetch_roads
    source_rate : spawn probability per step for open (boundary) road entries
    car_fraction : fraction of spawned vehicles that are cars

    Returns
    -------
    A validated Network ready for the simulation engine.
    """
    nodes = osm_data["nodes"]  # {node_id: {lat, lon}}
    ways = osm_data["ways"]    # [{id, nodes: [node_id, ...], tags: {...}}]

    # ------ Step 1: identify junction nodes ------
    # A node is a junction if it appears in 2+ different ways, or if it's an
    # endpoint of a way. We count how many way-endpoints and way-interiors
    # each node participates in.
    node_way_count: dict[int, int] = {}  # how many ways reference this node
    for way in ways:
        wnodes = way["nodes"]
        seen_in_way: set[int] = set()
        for nid in wnodes:
            if nid not in seen_in_way:
                node_way_count[nid] = node_way_count.get(nid, 0) + 1
                seen_in_way.add(nid)

    # Junction nodes: referenced by 2+ ways, OR are way endpoints
    way_endpoints: set[int] = set()
    for way in ways:
        wnodes = way["nodes"]
        if wnodes:
            way_endpoints.add(wnodes[0])
            way_endpoints.add(wnodes[-1])

    junction_node_ids: set[int] = set()
    for nid, count in node_way_count.items():
        if count >= 2:
            junction_node_ids.add(nid)
    # All way endpoints are potential junctions (they're either shared with
    # another way or they're dead ends that need source/sink behaviour)
    junction_node_ids |= way_endpoints

    # ------ Step 2: project coordinates ------
    # Simple equirectangular projection: (lat, lon) → (x, y) in meters
    # relative to the centroid of all junction nodes.
    jn_lats = [nodes[nid]["lat"] for nid in junction_node_ids if nid in nodes]
    jn_lons = [nodes[nid]["lon"] for nid in junction_node_ids if nid in nodes]
    if not jn_lats:
        logger.error("No junction nodes found — empty network")
        net = Network()
        net.validate()
        return net

    lat_ref = sum(jn_lats) / len(jn_lats)
    lon_ref = sum(jn_lons) / len(jn_lons)

    def project(lat: float, lon: float) -> tuple[float, float]:
        """Equirectangular projection to meters from the reference point."""
        x = (lon - lon_ref) * math.cos(math.radians(lat_ref)) * 111_320
        y = -(lat - lat_ref) * 110_540  # negative so north is up (lower y)
        return x, y

    # ------ Step 3: create junctions ------
    net = Network()
    junc_map: dict[int, int] = {}  # osm_node_id → junction_id
    jid = 0
    for nid in sorted(junction_node_ids):
        if nid not in nodes:
            continue
        x, y = project(nodes[nid]["lat"], nodes[nid]["lon"])
        net.add_junction(Junction(id=jid, x=x, y=y))
        junc_map[nid] = jid
        jid += 1

    # ------ Step 4: split ways into road segments ------
    rid = 0
    # Track which junction pairs are connected (to handle bidirectional roads)
    # For two-way roads we create roads in both directions.
    segments: list[dict[str, Any]] = []

    for way in ways:
        wnodes = way["nodes"]
        tags = way.get("tags", {})
        is_oneway = tags.get("oneway", "no") in ONEWAY_TRUE
        is_reverse = tags.get("oneway", "no") == "-1"
        road_name = tags.get("name", "")
        n_forward, n_backward, lanes_why = parse_lanes(tags)
        if is_reverse:
            # oneway=-1: the only travel direction runs end → start
            n_forward, n_backward = 0, n_forward
        logger.debug(
            "way %s (%s): %d forward + %d backward lanes (%s)",
            way.get("id"), road_name or "unnamed",
            n_forward, n_backward, lanes_why,
        )

        # Split the way at junction nodes
        # Find indices of junction nodes within this way
        junc_indices = [i for i, nid in enumerate(wnodes) if nid in junc_map]

        if len(junc_indices) < 2:
            # Way has fewer than 2 junction nodes — skip (e.g. a stub)
            continue

        # Create a segment between each consecutive pair of junction indices
        for seg_i in range(len(junc_indices) - 1):
            idx_a = junc_indices[seg_i]
            idx_b = junc_indices[seg_i + 1]
            seg_nodes = wnodes[idx_a:idx_b + 1]

            start_nid = seg_nodes[0]
            end_nid = seg_nodes[-1]
            if start_nid == end_nid:
                continue  # loop back to same node

            # Compute total path length along intermediate nodes
            total_m = 0.0
            for k in range(len(seg_nodes) - 1):
                n1, n2 = seg_nodes[k], seg_nodes[k + 1]
                if n1 in nodes and n2 in nodes:
                    total_m += haversine(
                        nodes[n1]["lat"], nodes[n1]["lon"],
                        nodes[n2]["lat"], nodes[n2]["lon"],
                    )

            n_cells = meters_to_cells(total_m)
            if n_cells < MIN_CELLS:
                continue  # too short for meaningful dynamics

            start_jid = junc_map[start_nid]
            end_jid = junc_map[end_nid]

            # Geometry: straight line from start junction to end junction
            x0, y0 = project(nodes[start_nid]["lat"], nodes[start_nid]["lon"])
            x1, y1 = project(nodes[end_nid]["lat"], nodes[end_nid]["lon"])
            geom_len = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
            if geom_len < 1e-6:
                continue  # degenerate geometry

            dx = (x1 - x0) / n_cells
            dy = (y1 - y0) / n_cells

            seg_info = {
                "start_jid": start_jid,
                "end_jid": end_jid,
                "n_cells": n_cells,
                "x0": x0, "y0": y0,
                "dx": dx, "dy": dy,
                "is_oneway": is_oneway,
                "is_reverse": is_reverse,
                "name": road_name,
                "n_forward": n_forward,
                "n_backward": n_backward,
                "street_id": f"w{way.get('id')}_s{seg_i}",
            }
            segments.append(seg_info)

    # ------ Step 5: create Road objects ------
    # Track connections for turn-proportion wiring
    # junction_incoming[jid] = list of road_ids whose head_junction == jid
    # junction_outgoing[jid] = list of road_ids whose tail_junction == jid
    junction_incoming: dict[int, list[int]] = {j: [] for j in net.junctions}
    junction_outgoing: dict[int, list[int]] = {j: [] for j in net.junctions}

    # Every segment becomes a `Street`. Its lanes are ordinary `Road`s — the
    # engine sees no difference — but they are grouped so the lateral pass
    # knows they are adjacent, and offset sideways so they render apart.
    for seg in segments:
        s_jid = seg["start_jid"]
        e_jid = seg["end_jid"]
        nc = seg["n_cells"]
        base_dx, base_dy = seg["dx"], seg["dy"]
        n_fwd, n_bwd = seg["n_forward"], seg["n_backward"]
        if seg["is_oneway"] and not seg["is_reverse"]:
            n_bwd = 0
        n_slots = n_fwd + n_bwd
        if n_slots <= 0:
            continue

        street = Street(
            seg["street_id"],
            baseline=(seg["x0"], seg["y0"],
                      seg["x0"] + base_dx * nc, seg["y0"] + base_dy * nc),
            lane_width=LANE_WIDTH_M,
        )
        # (direction, count, origin, step, head junction, tail junction)
        groups = (
            (FORWARD, n_fwd, (seg["x0"], seg["y0"]),
             (base_dx, base_dy), e_jid, s_jid),
            (BACKWARD, n_bwd, (seg["x0"] + base_dx * nc, seg["y0"] + base_dy * nc),
             (-base_dx, -base_dy), s_jid, e_jid),
        )
        for direction, count, (ox, oy), (ddx, ddy), head, tail in groups:
            for i in range(count):
                slot = street_slot(i, direction, n_fwd, n_bwd)
                # the perpendicular is taken from the *baseline*, so both
                # directions are offset along one consistent ruler
                lx, ly = offset_origin(
                    ox, oy, base_dx, base_dy, slot, n_slots, LANE_WIDTH_M
                )
                road = Road(
                    id=rid, length=nc, x0=lx, y0=ly, dx=ddx, dy=ddy,
                    periodic=False, head_junction=head, tail_junction=tail,
                )
                street.add_road(road, direction=direction, lane_index=i)
                junction_incoming[head].append(rid)
                junction_outgoing[tail].append(rid)
                rid += 1
        net.add_street(street)

    # ------ Step 6: set boundary source/sink behaviour ------
    # A road whose tail_junction has no incoming roads (no roads feeding it)
    # becomes a source. A road whose head_junction has no outgoing roads
    # becomes a sink (which it already is by default — just no junction transfer).
    # Actually: check which roads are dead-end entries/exits.
    for road in net.roads.values():
        if road.tail_junction is not None:
            # If this junction has outgoing roads but no incoming roads
            # feeding it, then this road can't receive junction transfers,
            # so make it a source.
            incoming_to_tail = junction_incoming.get(road.tail_junction, [])
            if not incoming_to_tail:
                road.source_rate = source_rate
                road.source_car_fraction = car_fraction
                road.tail_junction = None  # no junction feeds it

        if road.head_junction is not None:
            outgoing_from_head = junction_outgoing.get(road.head_junction, [])
            if not outgoing_from_head:
                # Dead-end exit: no outgoing roads → this is a sink
                road.head_junction = None  # vehicle exits the network

    # ------ Step 7: wire turn proportions ------
    # For each junction, for each incoming road, distribute evenly among all
    # outgoing roads (the default placeholder, editable via the map editor).
    for jid_key, j in net.junctions.items():
        incoming = junction_incoming.get(jid_key, [])
        outgoing = junction_outgoing.get(jid_key, [])
        if not incoming or not outgoing:
            continue

        j.turns = {}
        j.lane_links = {}
        for in_rid in incoming:
            # Exclude the reverse direction of the same segment (U-turn)
            # by checking if the outgoing road's tail_junction == this junction
            # and its head_junction == the incoming road's tail_junction
            valid_outs = []
            in_road = net.roads[in_rid]
            for out_rid in outgoing:
                out_road = net.roads[out_rid]
                # Avoid trivial U-turns: don't route back to where we came from
                if out_road.head_junction == in_road.tail_junction:
                    continue
                valid_outs.append(out_rid)

            if not valid_outs:
                # No valid outgoing roads (only U-turn available) — allow it
                valid_outs = list(outgoing)

            if not valid_outs:
                continue

            # every incoming lane may physically reach every outgoing lane;
            # v1 does not restrict by lane, but the graph is kept for later
            j.lane_links[in_rid] = list(valid_outs)

            # Turn proportions are a property of the junction, not of a lane:
            # split evenly across the outgoing *streets*, then enter that
            # street on the same lateral index (or its rightmost lane).
            groups = _group_by_street(net, valid_outs)
            chosen = [
                _matching_lane(net, lanes, in_road.lane_index)
                for lanes in groups
            ]
            even_p = round(1.0 / len(chosen), 6)
            turns = {oid: even_p for oid in chosen}
            # Fix rounding: adjust the last entry
            residual = round(1.0 - sum(turns.values()), 6)
            last = chosen[-1]
            turns[last] = round(turns[last] + residual, 6)
            j.turns[in_rid] = turns

    # ------ Step 8: clean up orphan junctions ------
    # Remove junctions that have no turns wired (no traffic passes through)
    orphan_jids = [jid_key for jid_key, j in net.junctions.items() if not j.turns]
    for jid_key in orphan_jids:
        # Disconnect roads from this orphan junction
        for road in net.roads.values():
            if road.head_junction == jid_key:
                road.head_junction = None
            if road.tail_junction == jid_key:
                road.tail_junction = None
                # Make it a source if it has no other feed
                road.source_rate = source_rate
                road.source_car_fraction = car_fraction
        del net.junctions[jid_key]

    # ------ Final validation ------
    # Remove roads that are completely disconnected (no junction, no source)
    # and wouldn't contribute anything to the simulation
    disconnected = [
        rid_key for rid_key, r in net.roads.items()
        if r.head_junction is None and r.tail_junction is None and r.source_rate <= 0
    ]
    for rid_key in disconnected:
        del net.roads[rid_key]

    # the cleanup passes above delete roads; keep the street registry honest
    net.prune_streets()

    try:
        net.validate()
    except ValueError as e:
        logger.warning("Network validation issue (fixing): %s", e)
        # Try to fix by removing problematic junctions
        _fix_validation(net)

    n_roads = len(net.roads)
    n_junctions = len(net.junctions)
    total_cells = sum(r.length for r in net.roads.values())
    logger.info(
        "OSM → Network: %d roads, %d junctions, %d total cells",
        n_roads, n_junctions, total_cells,
    )
    return net


def _group_by_street(net: Network, road_ids: list[int]) -> list[list[int]]:
    """
    Bucket outgoing lane ids by the street they belong to, order preserved.

    Only one direction of a street can leave a given junction, so a bucket is
    always one direction's lanes. A road with no street (there should be none
    after Stage 11, but map edits can add bare roads) is its own bucket.
    """
    order: list[Any] = []
    buckets: dict[Any, list[int]] = {}
    for rid in road_ids:
        road = net.roads[rid]
        key = road.street_id if road.street_id is not None else ("road", rid)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(rid)
    return [buckets[k] for k in order]


def _matching_lane(net: Network, lane_ids: list[int], lane_index: int) -> int:
    """
    Pick the outgoing lane a vehicle from `lane_index` continues into.

    Same lateral index where the outgoing street is wide enough, otherwise its
    rightmost lane — traffic merges inward rather than vanishing.
    """
    best = lane_ids[0]
    best_index = net.roads[best].lane_index
    for rid in lane_ids:
        idx = net.roads[rid].lane_index
        if idx == lane_index:
            return rid
        if idx > best_index:
            best, best_index = rid, idx
    return best


def _fix_validation(net: Network) -> None:
    """Try to fix turn-proportion issues in the network."""
    bad_junctions = []
    for jid, j in net.junctions.items():
        try:
            j.validate()
        except ValueError:
            bad_junctions.append(jid)

    for jid in bad_junctions:
        # Remove turns that reference non-existent roads
        j = net.junctions[jid]
        valid_turns: dict[int, dict[int, float]] = {}
        for in_rid, outs in j.turns.items():
            if in_rid not in net.roads:
                continue
            valid_outs = {o: p for o, p in outs.items() if o in net.roads}
            if valid_outs:
                # Renormalize
                total = sum(valid_outs.values())
                if total > 0:
                    valid_turns[in_rid] = {o: round(p / total, 6) for o, p in valid_outs.items()}
        j.turns = valid_turns

    # Final attempt
    try:
        net.validate()
    except ValueError as e:
        logger.error("Could not fix network validation: %s", e)
        # Remove remaining bad junctions
        for jid in bad_junctions:
            if jid in net.junctions:
                for r in net.roads.values():
                    if r.head_junction == jid:
                        r.head_junction = None
                    if r.tail_junction == jid:
                        r.tail_junction = None
                del net.junctions[jid]
