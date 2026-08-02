#!/usr/bin/env python3
"""
Independent verification script for ISSUE 1:
Do IIT BHU and IIEST Shibpur genuinely both produce 107 junctions,
or is there a bug causing identical counts?
"""
import sys
import os

# Add backend to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from src.mapdata.geocode import geocode
from src.mapdata.overpass_client import fetch_roads
from src.mapdata.osm_to_network import osm_to_network


def analyze_region(place_name: str):
    """Import a region and return detailed junction data."""
    print(f"\n{'=' * 60}")
    print(f"ANALYZING: {place_name}")
    print(f"{'=' * 60}")
    
    # Step 1: Geocode
    print(f"Step 1: Geocoding '{place_name}'...")
    bbox = geocode(place_name)
    if bbox is None:
        print(f"  ❌ Geocoding failed!")
        return None
    print(f"  → Bounding box: {bbox}")
    
    # Step 2: Fetch OSM data
    print(f"Step 2: Fetching OSM data...")
    osm_data = fetch_roads(*bbox)
    if osm_data is None:
        print(f"  ❌ OSM fetch failed!")
        return None
    print(f"  → OSM nodes: {len(osm_data['nodes'])}")
    print(f"  → OSM ways: {len(osm_data['ways'])}")
    
    # Step 3: Translate to Network
    print(f"Step 3: Translating to Network...")
    network = osm_to_network(osm_data, source_rate=0.3, car_fraction=0.3)
    print(f"  → Roads: {len(network.roads)}")
    print(f"  → Junctions: {len(network.junctions)}")
    print(f"  → Total cells: {sum(r.length for r in network.roads.values())}")
    
    # Step 4: Sample junction coordinates
    print(f"\nStep 4: First 10 junction coordinates (node ID, lat/lon approximation):")
    junction_samples = []
    for i, (jid, junction) in enumerate(sorted(network.junctions.items())[:10]):
        # Convert back to approximate lat/lon for verification
        # (we don't store original node IDs, but we can show projected x,y)
        junction_samples.append((jid, junction.x, junction.y))
        print(f"  J{jid:3d}: x={junction.x:8.1f}m, y={junction.y:8.1f}m")
    
    return {
        "place_name": place_name,
        "bbox": bbox,
        "osm_nodes": len(osm_data['nodes']),
        "osm_ways": len(osm_data['ways']),
        "roads": len(network.roads),
        "junctions": len(network.junctions),
        "total_cells": sum(r.length for r in network.roads.values()),
        "junction_samples": junction_samples,
        "network": network,
    }


def main():
    # Import both regions independently
    iit_bhu_data = analyze_region("IIT BHU Varanasi")
    iiest_data = analyze_region("IIEST Shibpur")
    
    # Compare results
    print(f"\n{'=' * 60}")
    print("COMPARISON:")
    print(f"{'=' * 60}")
    
    print(f"\nIIT BHU Varanasi:")
    print(f"  Bounding box: {iit_bhu_data['bbox']}")
    print(f"  OSM nodes: {iit_bhu_data['osm_nodes']}")
    print(f"  OSM ways: {iit_bhu_data['osm_ways']}")
    print(f"  Roads: {iit_bhu_data['roads']}")
    print(f"  Junctions: {iit_bhu_data['junctions']}")
    print(f"  Total cells: {iit_bhu_data['total_cells']}")
    
    print(f"\nIIEST Shibpur:")
    print(f"  Bounding box: {iiest_data['bbox']}")
    print(f"  OSM nodes: {iiest_data['osm_nodes']}")
    print(f"  OSM ways: {iiest_data['osm_ways']}")
    print(f"  Roads: {iiest_data['roads']}")
    print(f"  Junctions: {iiest_data['junctions']}")
    print(f"  Total cells: {iiest_data['total_cells']}")
    
    # Critical check: are the junction counts identical?
    if iit_bhu_data['junctions'] == iiest_data['junctions']:
        print(f"\n⚠️  WARNING: Both regions produced EXACTLY {iit_bhu_data['junctions']} junctions!")
        print(f"    This is suspicious and requires investigation.")
        
        # Check if bounding boxes are identical (would indicate caching bug)
        if iit_bhu_data['bbox'] == iiest_data['bbox']:
            print(f"    ❌ BLOCKER: Bounding boxes are IDENTICAL!")
            print(f"       This is a geocoding cache/fallback bug.")
        else:
            print(f"    ✓ Bounding boxes are different (geocoding works correctly).")
        
        # Check if junction coordinates overlap
        iit_coords = set((j[1], j[2]) for j in iit_bhu_data['junction_samples'])
        iiest_coords = set((j[1], j[2]) for j in iiest_data['junction_samples'])
        overlap = iit_coords & iiest_coords
        
        if overlap:
            print(f"    ❌ BLOCKER: Junction coordinates OVERLAP!")
            print(f"       {len(overlap)} identical coordinates found.")
            print(f"       This indicates the same physical junctions, not a coincidence.")
        else:
            print(f"    ✓ Junction coordinates are completely different.")
            print(f"       This may be a genuine coincidence (needs code review).")
    else:
        print(f"\n✓ Junction counts are DIFFERENT:")
        print(f"   IIT BHU: {iit_bhu_data['junctions']}")
        print(f"   IIEST Shibpur: {iiest_data['junctions']}")
        print(f"   → No coincidence bug detected.")
    
    # Check OSM data counts - these should definitely be different
    if (iit_bhu_data['osm_nodes'] == iiest_data['osm_nodes'] and 
        iit_bhu_data['osm_ways'] == iiest_data['osm_ways']):
        print(f"\n❌ CRITICAL: OSM raw data is IDENTICAL!")
        print(f"   This confirms a caching or API bug.")
    else:
        print(f"\n✓ OSM raw data is different (expected).")


if __name__ == "__main__":
    main()
