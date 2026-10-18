import pytest

from planner.domain.geo import Polyline, haversine_mi
from planner.services import routing
from planner.services.http import UpstreamError


def encode(points, precision=6):
    """Minimal polyline encoder (inverse of geo.decode_polyline) for building fixtures."""
    factor = 10**precision
    out, prev = [], (0, 0)
    for lat, lon in points:
        cur = (round(lat * factor), round(lon * factor))
        for delta in (cur[0] - prev[0], cur[1] - prev[1]):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev = cur
    return "".join(out)


def valhalla_trip(points, maneuvers, length_mi):
    return {
        "legs": [{"shape": encode(points), "maneuvers": maneuvers}],
        "summary": {"length": length_mi, "time": sum(m["time"] for m in maneuvers)},
    }


def test_valhalla_trip_spreads_maneuver_time_over_its_shape():
    pts = [(40.0, -100.0), (40.0, -99.5), (40.0, -99.0), (40.5, -99.0)]
    trip = valhalla_trip(
        pts,
        [
            {"begin_shape_index": 0, "end_shape_index": 2, "time": 3600, "length": 52.9, "street_names": ["I 80"]},
            {"begin_shape_index": 2, "end_shape_index": 3, "time": 1800, "length": 34.5, "street_names": ["Main St"]},
            {"begin_shape_index": 3, "end_shape_index": 3, "time": 0, "length": 0},
        ],
        length_mi=87.4,
    )
    route = routing._valhalla_trip(trip)
    assert route.drive_s == 5400
    assert route.line.cum_s == pytest.approx([0, 1800, 3600, 5400])
    assert route.line.length_mi == pytest.approx(87.4)  # scaled to the router's distance
    assert route.roads[0] == "I 80"


def test_road_refs_are_preferred_over_street_names():
    assert routing._main_roads({"Main St": 100, "I 80": 5, "US 30": 10}) == ["US 30", "I 80"]
    assert routing._main_roads({"Main St": 100}) == ["Main St"]


def straight(lat0, lon0, lat1, lon1, n=20):
    return Polyline([(lat0 + (lat1 - lat0) * k / n, lon0 + (lon1 - lon0) * k / n) for k in range(n + 1)])


def test_similarity_detects_overlapping_routes():
    a = straight(40, -100, 40, -98)
    assert routing.similarity(a, straight(40.005, -100, 40.005, -98)) > 0.95
    assert routing.similarity(a, straight(41, -100, 41, -98)) == 0


def test_via_candidates_sit_on_both_sides_of_the_midpoint():
    main = straight(40, -100, 40, -96)
    vias = routing.via_candidates(main, (40, -100), (40, -96))
    mid = main.point_at(main.length_mi / 2)
    assert vias[0][0] > mid[0] and vias[1][0] < mid[0]  # north, then south of an east-west trip
    assert haversine_mi(mid, vias[2]) == pytest.approx(2 * haversine_mi(mid, vias[0]), rel=0.01)


def make_route(lat_offset, hours=4.0):
    line = straight(40, -100, 40 + lat_offset, -96)
    line.cum_s = [hours * 3600 * d / line.length_mi for d in line.cum_mi]
    return routing.Route(line, line.length_mi, hours * 3600, "fake", [])


def test_get_routes_tops_up_with_via_routes(monkeypatch):
    calls = []

    def fake_valhalla(origin, destination, load_lb, via=None):
        calls.append(via)
        if via is None:
            return [make_route(0.0), make_route(0.002)]  # second one is a near-duplicate
        return [make_route(1.0 if via[0] > 40 else -1.0, hours=4.5)]

    monkeypatch.setattr(routing, "_valhalla", fake_valhalla)
    routes = routing.get_routes((40, -100), (40, -96), 40_000)
    assert len(routes) == 3
    assert [r.provider for r in routes] == ["fake", "fake+via", "fake+via"]
    assert calls[0] is None and len(calls) == 5


def test_get_routes_falls_back_to_osrm(monkeypatch):
    def broken(*args, **kwargs):
        raise UpstreamError("routing", "down")

    monkeypatch.setattr(routing, "_valhalla", broken)
    monkeypatch.setattr(
        routing, "_osrm", lambda o, d, via=None: [make_route(0.0), make_route(0.8, 4.2), make_route(-0.8, 4.3)]
    )
    routes = routing.get_routes((40, -100), (40, -96), 40_000)
    assert len(routes) == 3
    assert [r.drive_s for r in routes] == sorted(r.drive_s for r in routes)
