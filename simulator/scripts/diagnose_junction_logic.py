#!/usr/bin/env python3
"""
Deep dive into junction creation logic to understand why both regions
produce exactly 107 junctions.
"""
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from src.mapdata.geocode import geocode
from src.mapdata.overpass_client import fetch_roads
from collections import Counter


def analyze_junction_detection(place_name: str):
    """Trace junction detection step by step."""
    print(f"\n{'=' * 70}")
    print(f"JUNCTION DETECTION ANALYSIS: {place_name}")
    print(f"{'=' * 70}")
    
    bbox = geocode(place_name)
    if not bbox:
        return
    
    osm_data = fetch_roads(*bbox)
    if not osm_data:
        return
    
    nodes = osm_data["nodes"]
    ways = osm_data["ways"]
    
    print(f"\nRAW OSM DATA:")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Ways: {len(ways)}")
    
    # Replicate the junction detection logic from osm_to_network.py
    # ------ Step 1: count node appearances ------
    node_way_count = {}
    for way in ways:
        wnodes = way["nodes"]
        seen_in_way = set()
        for nid in wnodes:
            if nid not in seen_in_way:
                node_way_count[nid] = node_way_count.get(nid, 0) + 1
                seen_in_way.add(nid)
    
    # Junction nodes: referenced by 2+ ways, OR are way endpoints
    way_endpoints = set()
    for way in ways:
        wnodes = way["nodes"]
        if wnodes:
            way_endpoints.add(wnodes[0])
            way_endpoints.add(wnodes[-1])
    
    junction_node_ids = set()
    for nid, count in node_way_count.items():
        if count >= 2:
            junction_node_ids.add(nid)
    
    # All way endpoints are potential junctions
    junction_node_ids |= way_endpoints
    
    print(f"\nJUNCTION DETECTION:")
    print(f"  Nodes referenced by 2+ ways: {sum(1 for c in node_way_count.values() if c >= 2)}")
    print(f"  Way endpoints: {len(way_endpoints)}")
    print(f"  Total junction candidates (union): {len(junction_node_ids)}")
    
    # Check how many junction candidates are actually in the nodes dict
    valid_junctions = [nid for nid in junction_node_ids if nid in nodes]
    missing_nodes = [nid for nid in junction_node_ids if nid not in nodes]
    
    print(f"  Junction nodes with valid coordinates: {len(valid_junctions)}")
    print(f"  Junction nodes missing from node dict: {len(missing_nodes)}")
    
    # Distribution of node reference counts
    count_dist = Counter(node_way_count.values())
    print(f"\nNODE REFERENCE DISTRIBUTION:")
    for count in sorted(count_dist.keys()):
        print(f"  Referenced by {count} way(s): {count_dist[count]} nodes")
    
    # Check for any filtering or deduplication
    print(f"\nEXPECTED JUNCTION COUNT AFTER ORPHAN CLEANUP:")
    print(f"  This requires analyzing which junctions get wired with turns...")
    print(f"  (will be done by importing the full network)")
    
    return {
        "place": place_name,
        "raw_nodes": len(nodes),
        "raw_ways": len(ways),
        "junction_candidates": len(junction_node_ids),
        "valid_junctions": len(valid_junctions),
        "missing_nodes": len(missing_nodes),
    }


def main():
    iit_data = analyze_junction_detection("IIT BHU Varanasi")
    iiest_data = analyze_junction_detection("IIEST Shibpur")
    
    print(f"\n{'=' * 70}")
    print("SUMMARY COMPARISON:")
    print(f"{'=' * 70}")
    
    if iit_data and iiest_data:
        print(f"\nIIT BHU:")
        print(f"  Raw nodes: {iit_data['raw_nodes']}")
        print(f"  Junction candidates: {iit_data['junction_candidates']}")
        print(f"  Valid junctions: {iit_data['valid_junctions']}")
        
        print(f"\nIIEST Shibpur:")
        print(f"  Raw nodes: {iiest_data['raw_nodes']}")
        print(f"  Junction candidates: {iiest_data['junction_candidates']}")
        print(f"  Valid junctions: {iiest_data['valid_junctions']}")
        
        if iit_data['valid_junctions'] == iiest_data['valid_junctions']:
            print(f"\n⚠️  Both have {iit_data['valid_junctions']} valid junction candidates!")
            print(f"    The orphan cleanup step (Step 8 in osm_to_network.py)")
            print(f"    must be removing the EXACT SAME NUMBER of orphans in both cases.")
            print(f"    Let me check the actual network output...")


if __name__ == "__main__":
    main()
