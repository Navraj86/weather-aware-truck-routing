"""Small, dependency-free geometry helpers (lat/lon in degrees, distances in miles)."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field

EARTH_RADIUS_MI = 3958.7613

LatLon = tuple[float, float]


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    factor = 10**precision
    coords: list[LatLon] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _ in range(2):
            result = shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / factor, lon / factor))
    return coords


def interpolate(a: LatLon, b: LatLon, t: float) -> LatLon:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


@dataclass
class Polyline:
    """A route geometry with cumulative distance (miles) and drive time (seconds) per vertex."""

    points: list[LatLon]
    cum_mi: list[float] = field(default_factory=list)
    cum_s: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("A polyline needs at least two points")
        if not self.cum_mi:
            total = 0.0
            self.cum_mi = [0.0]
            for prev, cur in zip(self.points, self.points[1:]):
                total += haversine_mi(prev, cur)
                self.cum_mi.append(total)

    @property
    def length_mi(self) -> float:
        return self.cum_mi[-1]

    def _locate(self, distance_mi: float) -> tuple[int, float]:
        """Return (segment index, fraction along that segment) for a distance along the line."""
        d = min(max(distance_mi, 0.0), self.length_mi)
        i = bisect_right(self.cum_mi, d) - 1
        i = min(max(i, 0), len(self.points) - 2)
        seg = self.cum_mi[i + 1] - self.cum_mi[i]
        frac = 0.0 if seg <= 0 else (d - self.cum_mi[i]) / seg
        return i, frac

    def point_at(self, distance_mi: float) -> LatLon:
        i, frac = self._locate(distance_mi)
        return interpolate(self.points[i], self.points[i + 1], frac)

    def drive_seconds_at(self, distance_mi: float) -> float:
        if not self.cum_s:
            raise ValueError("Polyline has no time profile")
        i, frac = self._locate(distance_mi)
        return self.cum_s[i] + (self.cum_s[i + 1] - self.cum_s[i]) * frac

    def distance_at_drive_seconds(self, seconds: float) -> float:
        """Inverse of drive_seconds_at (cum_s is monotonic non-decreasing)."""
        s = min(max(seconds, 0.0), self.cum_s[-1])
        i = bisect_right(self.cum_s, s) - 1
        i = min(max(i, 0), len(self.points) - 2)
        span = self.cum_s[i + 1] - self.cum_s[i]
        frac = 0.0 if span <= 0 else (s - self.cum_s[i]) / span
        return self.cum_mi[i] + (self.cum_mi[i + 1] - self.cum_mi[i]) * frac

    def slice(self, start_mi: float, end_mi: float) -> list[LatLon]:
        """Coordinates of the sub-line between two distances (inclusive, interpolated ends)."""
        start_mi = max(0.0, start_mi)
        end_mi = min(self.length_mi, end_mi)
        if end_mi <= start_mi:
            p = self.point_at(start_mi)
            return [p, p]
        out = [self.point_at(start_mi)]
        i0 = bisect_right(self.cum_mi, start_mi)
        i1 = bisect_right(self.cum_mi, end_mi)
        out.extend(self.points[i0:i1])
        out.append(self.point_at(end_mi))
        return out

    def sample_every(self, step_mi: float) -> list[LatLon]:
        n = max(1, math.ceil(self.length_mi / step_mi))
        return [self.point_at(self.length_mi * k / n) for k in range(n + 1)]


def simplify_indices(points: list[LatLon], tolerance_deg: float) -> list[int]:
    """Iterative Douglas-Peucker; returns indices of kept vertices (always keeps endpoints)."""
    n = len(points)
    if n <= 2:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg * tolerance_deg
    while stack:
        first, last = stack.pop()
        ax, ay = points[first][1], points[first][0]
        bx, by = points[last][1], points[last][0]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best_i, best_d2 = -1, tol2
        for i in range(first + 1, last):
            px, py = points[i][1], points[i][0]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > best_d2:
                best_i, best_d2 = i, d2
        if best_i >= 0:
            keep[best_i] = True
            stack.append((first, best_i))
            stack.append((best_i, last))
    return [i for i, k in enumerate(keep) if k]


def mercator_y(lat: float) -> float:
    lat = max(min(lat, 85.0), -85.0)
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def inverse_mercator_y(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


def min_distance_mi(point: LatLon, samples: list[LatLon]) -> float:
    """Distance from a point to the nearest of a set of densely sampled points."""
    # Cheap equirectangular pre-filter, exact haversine for the winner.
    lat0 = math.radians(point[0])
    kx = math.cos(lat0)
    best, best_d2 = samples[0], float("inf")
    for s in samples:
        d2 = (s[0] - point[0]) ** 2 + ((s[1] - point[1]) * kx) ** 2
        if d2 < best_d2:
            best, best_d2 = s, d2
    return haversine_mi(point, best)
