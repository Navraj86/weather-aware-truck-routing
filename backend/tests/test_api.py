"""API tests with routing and weather replaced by deterministic fakes."""

from datetime import datetime, timedelta, timezone

import pytest
from rest_framework.test import APIClient

from planner.domain.geo import Polyline
from planner.services import planner as planner_service
from planner.services.http import UpstreamError
from planner.services.routing import Route
from planner.services.weather import HourlySeries


def fake_route(lat_offset: float, mph: float) -> Route:
    line = Polyline([(40.0, -100.0), (40.0 + lat_offset, -99.0), (40.0, -98.0)])
    drive_s = line.length_mi / mph * 3600
    line.cum_s = [0.0, drive_s / 2, drive_s]
    return Route(line, line.length_mi, drive_s, "fake", ["I 80"])


def storm_series(points, start, end):
    """Calm everywhere except a 50 mph wind band north of latitude 40.3."""
    t0 = int(start.timestamp()) // 3600 * 3600 - 3600
    times = [t0 + h * 3600 for h in range(int((end - start).total_seconds() // 3600) + 4)]
    out = []
    for lat, _ in points:
        wind = 50.0 if lat > 40.3 else 8.0
        n = len(times)
        out.append(
            HourlySeries(
                times,
                {
                    "wind_speed_10m": [wind] * n,
                    "wind_gusts_10m": [wind + 10] * n,
                    "rain": [0.0] * n,
                    "showers": [0.0] * n,
                    "snowfall": [0.0] * n,
                    "weather_code": [3] * n,
                },
            )
        )
    return out


@pytest.fixture
def client(monkeypatch):
    # Route A is fastest but bends north into the wind; B stays south.
    routes = [fake_route(0.8, 65), fake_route(0.05, 55)]
    monkeypatch.setattr(planner_service, "get_routes", lambda o, d, w: routes)
    monkeypatch.setattr(planner_service, "fetch_hourly", storm_series)
    return APIClient()


def body(**overrides):
    b = {
        "origin": {"lat": 40.0, "lon": -100.0, "label": "A"},
        "destination": {"lat": 40.0, "lon": -98.0, "label": "B"},
        "departure": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "load_lb": 20_000,
        "interval_mi": 10,
    }
    b.update(overrides)
    return b


def test_plan_recommends_the_route_that_avoids_severe_wind(client):
    r = client.post("/api/plan", body(), format="json")
    assert r.status_code == 200, r.content
    data = r.json()
    a, b = data["routes"]
    assert a["risk"]["severe_mi"] > 0 and b["risk"]["severe_mi"] == 0
    assert data["recommendation"]["route_id"] == "B"
    assert a["checkpoints"][0]["mile"] == 0 and a["checkpoints"][1]["mile"] == 10
    assert a["risk_segments"][0]["level"] == "low"
    assert {s["level"] for s in a["risk_segments"]} == {"low", "severe"}
    assert len(a["geometry"]) == len(a["drive_timeline"])


def test_heavy_load_turns_severe_wind_into_no_travel(client):
    data = client.post("/api/plan", body(load_lb=35_000), format="json").json()
    a = data["routes"][0]
    assert a["risk"]["no_travel_mi"] > 0
    assert a["risk"]["max_level"] == "no_travel"


def test_hos_adds_stops_and_travel_time(monkeypatch, client):
    long = fake_route(0.0, 1.0)  # absurdly slow so the trip exceeds 11 h of driving
    monkeypatch.setattr(planner_service, "get_routes", lambda o, d, w: [long])
    data = client.post("/api/plan", body(hos=True, interval_mi=50), format="json").json()
    route = data["routes"][0]
    assert route["travel_s"] > route["drive_s"]
    assert [s["kind"] for s in route["stops"]][:2] == ["break", "rest"]


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"interval_mi": 15}, "interval_mi"),
        ({"load_lb": -5}, "load_lb"),
        ({"departure": "2020-01-01T00:00:00Z"}, "departure"),
        ({"destination": {"lat": 40.0, "lon": -100.0}}, "non_field_errors"),
        ({"origin": {"lat": 95, "lon": 0}}, "origin"),
    ],
)
def test_plan_validation(client, overrides, field):
    r = client.post("/api/plan", body(**overrides), format="json")
    assert r.status_code == 400
    assert field in r.json()


def test_upstream_errors_are_reported(monkeypatch, client):
    def boom(*args):
        raise UpstreamError("weather", "rate limit reached, please retry in a minute", 503)

    monkeypatch.setattr(planner_service, "fetch_hourly", boom)
    r = client.post("/api/plan", body(), format="json")
    assert r.status_code == 503
    assert r.json() == {"error": "rate limit reached, please retry in a minute", "service": "weather"}


def test_heatmap(monkeypatch):
    from planner.services import heatmap

    monkeypatch.setattr(heatmap, "fetch_hourly", storm_series)
    corridor = [[40.0, -100.0], [40.5, -99.0], [40.0, -98.0]]
    departure = datetime.now(timezone.utc).replace(minute=20, second=0, microsecond=0) + timedelta(hours=1)
    r = APIClient().post(
        "/api/heatmap",
        {"corridors": [corridor], "departure": departure.isoformat(), "load_lb": 35_000},
        format="json",
    )
    assert r.status_code == 200, r.content
    data = r.json()
    # 48 h after a mid-hour departure spans 50 hourly frames.
    assert len(data["times"]) == 50
    assert data["times"][0] == int(departure.replace(minute=0).timestamp())
    assert len(data["layers"]["risk"]) == 50
    assert len(data["layers"]["wind"][0]) == len(data["cells"]) > 0
    assert set(data["layers"]["risk"][0]) <= {0, 4}  # calm, or 50 mph + 35k lb = No Travel
    assert data["bounds"]["north"] > 40.5 and data["bounds"]["south"] < 40.0


def test_health():
    assert APIClient().get("/api/health").json() == {"status": "ok"}
