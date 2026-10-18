"""Place search via Photon (OpenStreetMap data), plus raw "lat, lon" input."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.cache import cache

from .http import get_json

COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def search(query: str, limit: int = 6) -> list[dict]:
    query = query.strip()
    m = COORDS.match(query)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return [{"label": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon}]
        return []

    key = f"geo:{limit}:{query.lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = get_json(
        "geocoding",
        f"{settings.PHOTON_URL}/api/",
        params={"q": query, "limit": limit, "lang": "en"},
        timeout=10,
    )
    results = []
    seen = set()
    for f in data.get("features", []):
        lon, lat = f["geometry"]["coordinates"]
        label = _label(f.get("properties", {}))
        if label in seen:
            continue
        seen.add(label)
        results.append({"label": label, "lat": lat, "lon": lon})
    cache.set(key, results, 24 * 3600)
    return results


def _label(p: dict) -> str:
    name = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    parts = [name, p.get("city") if p.get("city") != name else None, p.get("state"), p.get("countrycode")]
    return ", ".join(x for x in parts if x) or "Unnamed place"
