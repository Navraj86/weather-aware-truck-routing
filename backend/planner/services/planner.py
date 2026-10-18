"""Trip planning: routes -> checkpoints -> forecast at ETA -> risk -> recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..domain.checkpoints import Checkpoint, aggregate_risk, build_checkpoints
from ..domain.geo import LatLon, Polyline, simplify_indices
from ..domain.hos import DriveClock
from ..domain.recommend import Candidate, recommend
from ..domain.risk import assess
from .routing import Route, get_routes
from .weather import fetch_hourly

ROUTE_IDS = "ABC"
SIMPLIFY_TOLERANCE_DEG = 0.0003  # ~30 m; keeps the line faithful while shrinking the payload ~10x
CORRIDOR_STEP_MI = 5.0


@dataclass(frozen=True)
class TripRequest:
    origin: LatLon
    destination: LatLon
    departure: datetime
    load_lb: float
    interval_mi: int
    hos: bool = False


def plan_trip(req: TripRequest) -> dict:
    clock = DriveClock(req.hos)
    routes = get_routes(req.origin, req.destination, req.load_lb)

    route_checkpoints = [build_checkpoints(r.line, req.interval_mi, req.departure, clock) for r in routes]
    _attach_weather(route_checkpoints, req.load_lb)

    candidates, payload = [], []
    for rid, route, cps in zip(ROUTE_IDS, routes, route_checkpoints):
        risk = aggregate_risk(cps)
        travel_s = clock.elapsed_s(route.drive_s)
        candidates.append(Candidate(rid, risk, travel_s))
        payload.append(_serialize_route(rid, route, cps, risk, travel_s, req, clock))

    return {
        "request": {
            "origin": {"lat": req.origin[0], "lon": req.origin[1]},
            "destination": {"lat": req.destination[0], "lon": req.destination[1]},
            "departure": _iso(req.departure),
            "load_lb": req.load_lb,
            "interval_mi": req.interval_mi,
            "hos": req.hos,
        },
        "routes": payload,
        "recommendation": recommend(candidates),
        "generated_at": _iso(datetime.now(timezone.utc)),
    }


def _attach_weather(route_checkpoints: list[list[Checkpoint]], load_lb: float) -> None:
    flat = [cp for cps in route_checkpoints for cp in cps]
    start = min(cp.eta for cp in flat)
    end = max(cp.eta for cp in flat)
    series = fetch_hourly([cp.point for cp in flat], start, end)
    for cp, s in zip(flat, series):
        cp.weather = s.sample(cp.eta)
        cp.risk = assess(cp.weather["wind_mph"], cp.weather["rain_in_hr"], cp.weather["snow_in_hr"], load_lb)


def _serialize_route(rid, route: Route, cps, risk, travel_s, req: TripRequest, clock: DriveClock) -> dict:
    line = route.line
    keep = simplify_indices(line.points, SIMPLIFY_TOLERANCE_DEG)
    return {
        "id": rid,
        "provider": route.provider,
        "roads": route.roads,
        "distance_mi": round(route.distance_mi, 1),
        "drive_s": round(route.drive_s),
        "travel_s": round(travel_s),
        "departure": _iso(req.departure),
        "arrival": _iso(req.departure + timedelta(seconds=travel_s)),
        "risk": risk.to_dict(),
        "geometry": [[round(line.points[i][1], 5), round(line.points[i][0], 5)] for i in keep],
        # Cumulative driving seconds per geometry vertex, for placing the truck at any time.
        "drive_timeline": [round(line.cum_s[i]) for i in keep],
        "risk_segments": _risk_segments(line, cps),
        "checkpoints": [_serialize_checkpoint(cp) for cp in cps],
        "stops": _serialize_stops(line, clock, route.drive_s, req.departure),
        "corridor": [[round(p[0], 4), round(p[1], 4)] for p in line.sample_every(CORRIDOR_STEP_MI)],
    }


def _serialize_checkpoint(cp: Checkpoint) -> dict:
    return {
        "index": cp.index,
        "mile": round(cp.distance_mi, 1),
        "lat": round(cp.point[0], 5),
        "lon": round(cp.point[1], 5),
        "eta": _iso(cp.eta),
        "covers_mi": [round(cp.covers_from_mi, 2), round(cp.covers_to_mi, 2)],
        "weather": cp.weather,
        "risk": cp.risk.to_dict() if cp.risk else None,
    }


def _risk_segments(line: Polyline, cps: list[Checkpoint]) -> list[dict]:
    """Merge consecutive checkpoints of equal level into coloured stretches of road."""
    segments: list[dict] = []
    for cp in cps:
        level = cp.risk.level.key if cp.risk else "low"
        if segments and segments[-1]["level"] == level:
            segments[-1]["to_mi"] = cp.covers_to_mi
        else:
            segments.append({"level": level, "from_mi": cp.covers_from_mi, "to_mi": cp.covers_to_mi})
    for s in segments:
        coords = line.slice(s["from_mi"], s["to_mi"])
        keep = simplify_indices(coords, SIMPLIFY_TOLERANCE_DEG)
        s["coords"] = [[round(coords[i][1], 5), round(coords[i][0], 5)] for i in keep]
        s["from_mi"], s["to_mi"] = round(s["from_mi"], 2), round(s["to_mi"], 2)
    return segments


def _serialize_stops(line: Polyline, clock: DriveClock, drive_s: float, departure: datetime) -> list[dict]:
    out = []
    for stop in clock.stops(drive_s):
        lat, lon = line.point_at(line.distance_at_drive_seconds(stop.drive_s))
        # elapsed_s() at the stop's own drive time does not yet include that stop.
        begins = clock.elapsed_s(stop.drive_s)
        out.append(
            {
                "kind": stop.kind,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "drive_s": round(stop.drive_s),
                "start": _iso(departure + timedelta(seconds=begins)),
                "end": _iso(departure + timedelta(seconds=begins + stop.duration_s)),
            }
        )
    return out


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
