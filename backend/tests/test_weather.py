from datetime import datetime, timedelta, timezone

import pytest

from planner.services import weather
from planner.services.weather import HourlySeries, snap

T0 = 1_767_268_800  # 2026-01-01T12:00Z


def series(**overrides):
    values = {
        "wind_speed_10m": [10.0, 20.0, 30.0],
        "wind_gusts_10m": [15.0, 25.0, 35.0],
        "rain": [0.0, 0.2, 0.4],
        "showers": [0.0, 0.05, 0.0],
        "snowfall": [0.0, 0.0, 1.5],
        "weather_code": [0, 61, 73],
    }
    values.update(overrides)
    return HourlySeries([T0, T0 + 3600, T0 + 7200], values)


def at(seconds: float) -> datetime:
    return datetime.fromtimestamp(T0 + seconds, tz=timezone.utc)


def test_wind_is_interpolated_linearly():
    assert series().sample(at(1800))["wind_mph"] == 15.0
    assert series().sample(at(5400))["gust_mph"] == 30.0


def test_precipitation_uses_the_hour_that_contains_the_eta():
    # Values at T0+1h are totals for (T0, T0+1h], so an ETA of T0+30min reads them.
    s = series().sample(at(1800))
    assert s["rain_in_hr"] == pytest.approx(0.25)  # rain + showers
    assert s["description"] == "Light rain"
    assert series().sample(at(3600))["rain_in_hr"] == pytest.approx(0.25)
    assert series().sample(at(3601))["snow_in_hr"] == 1.5


def test_missing_values_are_flagged():
    s = series(wind_speed_10m=[None, None, None]).sample(at(0))
    assert s["missing"] is True and s["wind_mph"] == 0.0


def test_snap_groups_nearby_points():
    assert snap((41.8781, -87.6298)) == snap((41.88, -87.64)) == (41.9, -87.65)


def test_fetch_hourly_dedupes_and_caches(monkeypatch):
    calls = []

    def fake_request(points, start, end):
        calls.append(list(points))
        return [series() for _ in points]

    monkeypatch.setattr(weather, "_request", fake_request)
    pts = [(41.878, -87.63), (41.879, -87.631), (38.627, -90.199)]
    start, end = at(0), at(7200)
    out = weather.fetch_hourly(pts, start, end)
    assert len(out) == 3 and len(calls) == 1 and len(calls[0]) == 2

    weather.fetch_hourly(pts, start, end)
    assert len(calls) == 1  # second call served from cache


def test_fetch_window_buckets_requests_for_cache_reuse():
    now = datetime(2026, 1, 1, 12, 40, tzinfo=timezone.utc)
    base, days = weather.fetch_window(now, now + timedelta(hours=30), now=now)
    assert base == datetime(2026, 1, 1, 11, tzinfo=timezone.utc) and days == 2
    # A later departure in the same hour maps onto the same base, just a longer bucket.
    base2, days2 = weather.fetch_window(now + timedelta(days=3), now + timedelta(days=4), now=now)
    assert base2 == base and days2 == 7


def test_fetch_window_rejects_trips_beyond_the_forecast():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(weather.UpstreamError):
        weather.fetch_window(now, now + timedelta(days=15), now=now)


def test_get_json_retries_dropped_connections(monkeypatch):
    import requests

    from planner.services import http

    class Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

    attempts = []

    def flaky_get(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError("reset by peer")
        return Resp()

    monkeypatch.setattr(http.session(), "get", flaky_get)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    assert http.get_json("weather", "https://example.test", retries=2) == {"ok": True}
    assert len(attempts) == 3

    attempts.clear()
    with pytest.raises(http.UpstreamError):
        http.get_json("weather", "https://example.test", retries=1)
