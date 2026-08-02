"""
geocode.py — place-name → bounding box via Nominatim (OSM's free geocoder).

Nominatim returns results ranked by relevance. We pick the first result and
log what was chosen so the user knows which geographic match was used.
Multiple / ambiguous results are handled explicitly: the first result is used,
all candidates are logged.

Returns:
    A (south, west, north, east) bounding box in decimal degrees,
    or None if the query failed / returned no results.
"""

from __future__ import annotations

import logging
import urllib.request
import urllib.error
import urllib.parse
import json
from typing import Any

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "CA-Rule184-TrafficSim/1.0 (academic-research)"


def geocode(place_name: str, timeout: float = 15.0) -> tuple[float, float, float, float] | None:
    """
    Query Nominatim for a place name and return a bounding box.

    Returns (south, west, north, east) as floats, or None on failure.
    """
    params = urllib.parse.urlencode({
        "q": place_name,
        "format": "json",
        "limit": "5",
        "addressdetails": "1",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: list[dict[str, Any]] = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.error("Nominatim query failed for %r: %s", place_name, exc)
        return None

    if not data:
        logger.warning("Nominatim returned no results for %r", place_name)
        return None

    # Log all candidates so ambiguity is visible
    for i, r in enumerate(data):
        logger.info(
            "  Nominatim result %d: %s (type=%s, class=%s)",
            i, r.get("display_name", "?"), r.get("type", "?"), r.get("class", "?"),
        )

    # Prefer amenity/boundary/place/landuse over specific building results
    chosen = data[0]
    for r in data:
        cls = r.get("class", "")
        typ = r.get("type", "")
        if cls in ("amenity", "boundary", "place", "landuse") or typ in ("university", "campus"):
            chosen = r
            break

    bbox = chosen.get("boundingbox")  # [south, north, west, east] as strings
    if not bbox or len(bbox) < 4:
        logger.error("Nominatim result has no bounding box: %s", chosen.get("display_name"))
        return None

    south, north, west, east = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

    # Ensure minimum bounding box size of ~0.006 degrees (~650m) for campus networks
    min_span = 0.006
    lat_span = north - south
    lon_span = east - west
    if lat_span < min_span:
        mid_lat = (south + north) / 2.0
        south = mid_lat - min_span / 2.0
        north = mid_lat + min_span / 2.0
    if lon_span < min_span:
        mid_lon = (west + east) / 2.0
        west = mid_lon - min_span / 2.0
        east = mid_lon + min_span / 2.0

    logger.info(
        "Geocoded %r → %s  bbox=(%.5f, %.5f, %.5f, %.5f)",
        place_name, chosen.get("display_name", "?"), south, west, north, east,
    )
    return (south, west, north, east)
