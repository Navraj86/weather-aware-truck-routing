"""Route options from Valhalla (truck costing) with an OSRM fallback.

Valhalla's public server supports truck routing with the vehicle's weight and
returns up to two alternates. If fewer than three distinct routes come back we
synthesise more by forcing the route through a via point offset to either side
of the main route's midpoint.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

from django.conf import settings

from ..domain.geo import LatLon, Polyline, decode_polyline, haversine_mi, min_distance_mi
from .http import UpstreamError, get_json, post_json

log = logging.getLogger(__name__)

LB_PER_METRIC_TON = 2204.62
ROUTE_COUNT = 3
# Route references such as "I 80", "I-55 S", "US 30", "SR 99".
ROAD_REF = re.compile(r"^[A-Z]{1,3}[- ]?\d+")


@dataclass
class Route:
    line: Polyline
    distance_mi: float
    drive_s: float
    provider: str
    roads: list[str]


def get_routes(origin: LatLon, destination: LatLon, load_lb: float) -> list[Route]:
    try:
        routes = _valhalla(origin, destination, load_lb)
        route_via = partial(_valhalla, origin, destination, load_lb)
    except UpstreamError as exc:
        log.warning("Valhalla failed, falling back to OSRM: %s", exc)
        routes = _osrm(origin, destination)
        route_via = partial(_osrm, origin, destination)

    routes = _dedupe(routes)
    if len(routes) < ROUTE_COUNT:
        routes = _add_via_alternatives(routes, origin, destination, route_via)
    routes.sort(key=lambda r: r.drive_s)
    return routes[:ROUTE_COUNT]


# --------------------------------------------------------------------------- Valhalla


def _valhalla(origin: LatLon, destination: LatLon, load_lb: float, via: LatLon | None = None) -> list[Route]:
    locations = [{"lat": origin[0], "lon": origin[1]}]
    if via:
        locations.append({"lat": via[0], "lon": via[1], "type": "through", "radius": 25000})
    locations.append({"lat": destination[0], "lon": destination[1]})
    payload = {
        "locations": locations,
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(max(load_lb, 1) / LB_PER_METRIC_TON, 2)}},
        "units": "miles",
        "directions_options": {"units": "miles"},
        "alternates": 0 if via else ROUTE_COUNT - 1,
    }
    data = post_json("routing", f"{settings.VALHALLA_URL}/route", payload, timeout=45)
    if "trip" not in data:
        raise UpstreamError("routing", data.get("error", "no route found"), 422)
    trips = [data["trip"]] + [a["trip"] for a in data.get("alternates", []) if "trip" in a]
    return [_valhalla_trip(t) for t in trips]


def _valhalla_trip(trip: dict) -> Route:
    points: list[LatLon] = []
    seconds_per_point: list[float] = []
    road_miles: dict[str, float] = defaultdict(float)
    for leg in trip["legs"]:
        shape = decode_polyline(leg["shape"], 6)
        offset = len(points)
        if offset:  # legs share their joining vertex
            shape = shape[1:]
            offset -= 1
        points.extend(shape)
        seconds_per_point.extend([0.0] * len(shape))
        for m in leg.get("maneuvers", []):
            begin, end = m["begin_shape_index"] + offset, m["end_shape_index"] + offset
            _spread_time(points, seconds_per_point, begin, end, float(m.get("time", 0.0)))
            for name in m.get("street_names", [])[:1]:
                road_miles[name] += float(m.get("length", 0.0))

    summary = trip["summary"]
    distance_mi = float(summary["length"])
    line = _line_with_time(points, seconds_per_point, distance_mi)
    return Route(line, distance_mi, float(summary["time"]), "valhalla-truck", _main_roads(road_miles))


def _spread_time(points: list[LatLon], seg_s: list[float], begin: int, end: int, total_s: float) -> None:
    """Distribute a maneuver's time over its shape segments, proportional to segment length.

    seg_s[i] holds the seconds needed to travel from point i-1 to point i.
    """
    if end <= begin or total_s <= 0:
        return
    lengths = [haversine_mi(points[i - 1], points[i]) for i in range(begin + 1, end + 1)]
    total_len = sum(lengths)
    for k, i in enumerate(range(begin + 1, end + 1)):
        seg_s[i] += total_s * (lengths[k] / total_len if total_len else 1 / len(lengths))


def _line_with_time(points: list[LatLon], seg_s: list[float], distance_mi: float) -> Polyline:
    """Polyline with cumulative drive time, with mileage scaled to the router's reported distance
    (so checkpoint miles and risk miles add up to exactly the distance shown)."""
    cum, acc = [], 0.0
    for s in seg_s:
        acc += s
        cum.append(acc)
    cum[0] = 0.0
    line = Polyline(points)
    if line.length_mi > 0:
        k = distance_mi / line.length_mi
        line.cum_mi = [d * k for d in line.cum_mi]
    line.cum_s = cum
    return line


def _main_roads(road_miles: dict[str, float], limit: int = 3) -> list[str]:
    refs = sorted(((mi, n) for n, mi in road_miles.items() if ROAD_REF.match(n)), reverse=True)
    if not refs:
        refs = sorted(((mi, n) for n, mi in road_miles.items()), reverse=True)
    return [n for _, n in refs[:limit]]


# --------------------------------------------------------------------------- OSRM fallback


def _osrm(origin: LatLon, destination: LatLon, via: LatLon | None = None) -> list[Route]:
    pts = [origin] + ([via] if via else []) + [destination]
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in pts)
    data = get_json(
        "routing",
        f"{settings.OSRM_URL}/route/v1/driving/{coords}",
        params={
            "alternatives": "false" if via else "3",
            "overview": "full",
            "geometries": "polyline6",
            "annotations": "duration",
            "steps": "true",
        },
        timeout=45,
    )
    if data.get("code") != "Ok" or not data.get("routes"):
        raise UpstreamError("routing", data.get("message", "no route found"), 422)
    out = []
    for r in data["routes"]:
        points = decode_polyline(r["geometry"], 6)
        seg_s = [0.0]
        road_miles: dict[str, float] = defaultdict(float)
        for leg in r["legs"]:
            seg_s.extend(leg["annotation"]["duration"])
            for step in leg.get("steps", []):
                name = step.get("ref") or step.get("name")
                if name:
                    road_miles[name.split(";")[0]] += step["distance"] / 1609.344
        seg_s = (seg_s + [0.0] * len(points))[: len(points)]
        distance_mi = r["distance"] / 1609.344
        out.append(
            Route(_line_with_time(points, seg_s, distance_mi), distance_mi, float(r["duration"]), "osrm-car", _main_roads(road_miles))
        )
    return out


# --------------------------------------------------------------------------- alternatives


def similarity(a: Polyline, b: Polyline, tolerance_mi: float = 1.5) -> float:
    """Fraction of route a lying within `tolerance_mi` of route b."""
    a_pts = a.sample_every(max(a.length_mi / 150, 2.0))
    b_pts = b.sample_every(max(b.length_mi / 600, 0.5))
    near = sum(1 for p in a_pts if min_distance_mi(p, b_pts) <= tolerance_mi)
    return near / len(a_pts)


def _is_duplicate(candidate: Route, kept: list[Route]) -> bool:
    for r in kept:
        if abs(candidate.distance_mi - r.distance_mi) / max(r.distance_mi, 1) > 0.15:
            continue
        if similarity(candidate.line, r.line) > 0.92 and similarity(r.line, candidate.line) > 0.92:
            return True
    return False


def _dedupe(routes: list[Route]) -> list[Route]:
    kept: list[Route] = []
    for r in routes:
        if not _is_duplicate(r, kept):
            kept.append(r)
    return kept


def via_candidates(main: Polyline, origin: LatLon, destination: LatLon) -> list[LatLon]:
    """Points offset perpendicular to the trip at the main route's midpoint, alternating sides."""
    straight = haversine_mi(origin, destination)
    mid = main.point_at(main.length_mi / 2)
    lat0 = math.radians((origin[0] + destination[0]) / 2)
    # Direction of travel in a local flat frame (x east, y north, miles).
    dx = (destination[1] - origin[1]) * 69.172 * math.cos(lat0)
    dy = (destination[0] - origin[0]) * 69.0
    norm = math.hypot(dx, dy) or 1.0
    px, py = -dy / norm, dx / norm
    base = min(max(straight * 0.18, 12.0), 140.0)
    out = []
    for mult in (1, -1, 2, -2):
        off = base * mult
        out.append((mid[0] + py * off / 69.0, mid[1] + px * off / (69.172 * math.cos(math.radians(mid[0])))))
    return out


def _add_via_alternatives(routes: list[Route], origin, destination, route_via) -> list[Route]:
    if not routes:
        return routes
    vias = via_candidates(routes[0].line, origin, destination)

    def attempt(via):
        try:
            found = route_via(via=via)
            return found[0] if found else None
        except UpstreamError as exc:
            log.info("Via-point alternative failed: %s", exc)
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        candidates = list(pool.map(attempt, vias))
    for c in candidates:
        if len(routes) >= ROUTE_COUNT:
            break
        # Reject detours that are wildly longer than the fastest route.
        if c and c.drive_s < routes[0].drive_s * 1.6 and not _is_duplicate(c, routes):
            c.provider += "+via"
            routes.append(c)
    return routes
