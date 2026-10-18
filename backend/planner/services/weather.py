"""Hourly forecasts from Open-Meteo, batched, de-duplicated and cached.

Units requested: wind in mph, precipitation and snowfall in inches. Open-Meteo
reports rain/showers/snowfall as the amount fallen during the *preceding* hour,
which is exactly an in/hr rate. Wind is an instantaneous value at the hour.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from ..domain.geo import LatLon
from .http import UpstreamError, get_json

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "weather_code")
SNAP_DEG = 0.05  # ~3.5 mi; finer than the forecast models' grid, coarse enough to dedupe nearby points
CHUNK = 100  # locations per request (keeps the URL well under 4 kB)
CACHE_TTL_S = 60 * 60
WINDOW_DAYS = (2, 4, 7, 11, 14)  # up to 14 days counts as a single API call per location

WMO_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers",
    81: "Rain showers", 82: "Violent rain showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


@dataclass
class HourlySeries:
    times: list[int]  # unix seconds, on the hour, ascending
    values: dict[str, list[float | None]]

    def _at(self, var: str, i: int) -> float | None:
        return self.values[var][i]

    def linear(self, var: str, t: float) -> float | None:
        """Linear interpolation between hourly instants (for wind)."""
        times = self.times
        if t <= times[0]:
            return self._at(var, 0)
        if t >= times[-1]:
            return self._at(var, len(times) - 1)
        i = bisect_right(times, t) - 1
        a, b = self._at(var, i), self._at(var, i + 1)
        if a is None or b is None:
            return a if b is None else b
        frac = (t - times[i]) / (times[i + 1] - times[i])
        return a + (b - a) * frac

    def hour_ending(self, var: str, t: float) -> float | None:
        """Value for the hour containing t, i.e. the first timestamp >= t (for accumulations)."""
        i = min(bisect_left(self.times, t), len(self.times) - 1)
        return self._at(var, i)

    def sample(self, t: datetime) -> dict:
        ts = t.timestamp()
        wind = self.linear("wind_speed_10m", ts)
        gust = self.linear("wind_gusts_10m", ts)
        rain = self.hour_ending("rain", ts)
        showers = self.hour_ending("showers", ts)
        snow = self.hour_ending("snowfall", ts)
        code = self.hour_ending("weather_code", ts)  # describes the same hour as the precipitation
        missing = wind is None or (rain is None and showers is None) or snow is None
        return {
            "wind_mph": round(wind or 0.0, 1),
            "gust_mph": round(gust or 0.0, 1),
            "rain_in_hr": round((rain or 0.0) + (showers or 0.0), 3),
            "snow_in_hr": round(snow or 0.0, 3),
            "weather_code": int(code) if code is not None else None,
            "description": WMO_CODES.get(int(code), "Unknown") if code is not None else "No data",
            "missing": missing,
        }


def snap(p: LatLon) -> LatLon:
    return (round(round(p[0] / SNAP_DEG) * SNAP_DEG, 4), round(round(p[1] / SNAP_DEG) * SNAP_DEG, 4))


def hour_floor(t: datetime) -> datetime:
    return t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def hour_ceil(t: datetime) -> datetime:
    f = hour_floor(t)
    return f if f == t.astimezone(timezone.utc) else f + timedelta(hours=1)


def fetch_window(start: datetime, end: datetime, now: datetime | None = None) -> tuple[datetime, int]:
    """Canonical (first hour, days) request window covering [start, end].

    Windows start an hour before the current hour and come in a few fixed
    lengths, so different trips planned within the same hour share cache
    entries instead of each asking Open-Meteo for a slightly different range.
    """
    now = now or datetime.now(timezone.utc)
    base = hour_floor(min(now, start)) - timedelta(hours=1)
    needed = hour_ceil(end) + timedelta(hours=1)
    for days in WINDOW_DAYS:
        if base + timedelta(days=days) >= needed:
            return base, days
    raise UpstreamError("weather", "the trip extends beyond the 14-day forecast range", 422)


def fetch_hourly(points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
    """Hourly series covering [start, end] for each point (aligned with the input order)."""
    base, days = fetch_window(start, end)
    usable_days = [d for d in WINDOW_DAYS if d >= days]

    def key(p: LatLon, d: int) -> str:
        return f"om:{p[0]}:{p[1]}:{base:%Y%m%d%H}:{d}"

    snapped = [snap(p) for p in points]
    unique = list(dict.fromkeys(snapped))
    # Any cached window at least as long as the one we need will do.
    cached = cache.get_many([key(p, d) for p in unique for d in usable_days])
    found: dict[LatLon, HourlySeries] = {}
    for p in unique:
        for d in usable_days:
            if key(p, d) in cached:
                found[p] = cached[key(p, d)]
                break

    missing = [p for p in unique if p not in found]
    chunks = [missing[i : i + CHUNK] for i in range(0, len(missing), CHUNK)]
    if chunks:
        end_h = base + timedelta(days=days)
        # Open-Meteo's free tier drops connections on bursts, so keep concurrency low.
        with ThreadPoolExecutor(max_workers=min(2, len(chunks))) as pool:
            for chunk, series in zip(chunks, pool.map(lambda c: _request(c, base, end_h), chunks)):
                for p, s in zip(chunk, series):
                    found[p] = s
        cache.set_many({key(p, days): found[p] for p in missing}, CACHE_TTL_S)

    return [found[p] for p in snapped]


def _request(points: list[LatLon], start_h: datetime, end_h: datetime) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": f"{start_h:%Y-%m-%dT%H:%M}",
        "end_hour": f"{end_h:%Y-%m-%dT%H:%M}",
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    data = get_json("weather", f"{settings.OPEN_METEO_URL}/v1/forecast", params=params, timeout=30, retries=2)
    items = data if isinstance(data, list) else [data]
    out = []
    for item in items:
        hourly = item["hourly"]
        out.append(HourlySeries(hourly["time"], {v: hourly[v] for v in HOURLY_VARS}))
    return out
