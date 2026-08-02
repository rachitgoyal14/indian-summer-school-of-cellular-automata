"""
overpass_client.py — query the Overpass API for roads within a bounding box.

Returns the raw OSM graph: nodes (with lat/lon) and ways (sequences of node
refs + tags including highway type, name, oneway). This raw data is consumed
by osm_to_network.py to build a simulator Network.

The Overpass API has rate limits and occasional downtime; all failures are
caught and reported clearly rather than crashing the import.
"""

from __future__ import annotations

import logging
import urllib.request
import urllib.error
import urllib.parse
import json
from typing import Any

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "CA-Rule184-TrafficSim/1.0 (academic-research)"

# We query for highway=* ways and their nodes within the bounding box.
# Include vehicular roads and service roads (common on university campuses).
OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;
"""


def fetch_roads(
    south: float,
    west: float,
    north: float,
    east: float,
    timeout: int = 60,
) -> dict[str, Any] | None:
    """
    Query the Overpass API for all vehicular roads within a bounding box.

    Returns a dict with:
        "nodes": {node_id: {"lat": float, "lon": float}}
        "ways": [{
            "id": int,
            "nodes": [node_id, ...],
            "tags": {"highway": "...", "name": "...", "oneway": "yes/no", ...}
        }]

    Returns None with a logged error on failure.
    """
    query = OVERPASS_QUERY_TEMPLATE.format(
        south=south, west=west, north=north, east=east, timeout=timeout,
    )
    data = _raw_overpass_query(query, timeout=timeout + 10)
    if data is None:
        return None

    elements = data.get("elements", [])
    nodes: dict[int, dict[str, float]] = {}
    ways: list[dict[str, Any]] = []

    for el in elements:
        if el.get("type") == "node":
            nodes[el["id"]] = {"lat": el["lat"], "lon": el["lon"]}
        elif el.get("type") == "way":
            ways.append({
                "id": el["id"],
                "nodes": el.get("nodes", []),
                "tags": el.get("tags", {}),
            })

    logger.info(
        "Overpass returned %d nodes, %d ways for bbox (%.4f, %.4f, %.4f, %.4f)",
        len(nodes), len(ways), south, west, north, east,
    )
    return {"nodes": nodes, "ways": ways}


OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = "CA-Rule184-TrafficSim/1.0 (academic-research)"


def _raw_overpass_query(query: str, timeout: int = 70) -> dict[str, Any] | None:
    """Send a query to Overpass API endpoints (with fallback to mirrors)."""
    encoded = urllib.parse.urlencode({"data": query}).encode("utf-8")
    
    for endpoint in OVERPASS_ENDPOINTS:
        req = urllib.request.Request(
            endpoint,
            data=encoded,
            headers={"User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            logger.info("Sending query to Overpass endpoint: %s", endpoint)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode()[:300]
            except Exception:
                pass
            logger.warning("Overpass endpoint %s returned HTTP %d: %s", endpoint, exc.code, body)
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("Overpass endpoint %s failed: %s", endpoint, exc)

    logger.error("All Overpass endpoints failed.")
    return None


