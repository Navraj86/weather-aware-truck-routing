"""Checkpoint placement along a route and per-route risk aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .geo import LatLon, Polyline
from .hos import DriveClock
from .risk import RiskAssessment, RiskLevel

ALLOWED_INTERVALS_MI = (10, 25, 50)


@dataclass
class Checkpoint:
    index: int
    distance_mi: float
    point: LatLon
    drive_s: float
    eta: datetime
    # The stretch of road this checkpoint represents (half-way to each neighbour).
    covers_from_mi: float
    covers_to_mi: float
    weather: dict | None = None
    risk: RiskAssessment | None = None

    @property
    def covered_mi(self) -> float:
        return self.covers_to_mi - self.covers_from_mi


def checkpoint_distances(length_mi: float, interval_mi: float) -> list[float]:
    """0, interval, 2*interval, ... plus the destination."""
    if interval_mi <= 0:
        raise ValueError("interval must be positive")
    out = []
    d = 0.0
    while d < length_mi - 1e-6:
        out.append(d)
        d += interval_mi
    out.append(length_mi)
    # A destination that lands within half a mile of the last checkpoint replaces it.
    if len(out) > 2 and out[-1] - out[-2] < 0.5:
        out.pop(-2)
    return out


def build_checkpoints(
    line: Polyline, interval_mi: float, departure: datetime, clock: DriveClock
) -> list[Checkpoint]:
    distances = checkpoint_distances(line.length_mi, interval_mi)
    checkpoints: list[Checkpoint] = []
    for i, d in enumerate(distances):
        lo = 0.0 if i == 0 else (distances[i - 1] + d) / 2
        hi = line.length_mi if i == len(distances) - 1 else (d + distances[i + 1]) / 2
        drive_s = line.drive_seconds_at(d)
        checkpoints.append(
            Checkpoint(
                index=i,
                distance_mi=d,
                point=line.point_at(d),
                drive_s=drive_s,
                eta=departure + timedelta(seconds=clock.elapsed_s(drive_s)),
                covers_from_mi=lo,
                covers_to_mi=hi,
            )
        )
    return checkpoints


@dataclass
class RouteRisk:
    miles_by_level: dict[RiskLevel, float] = field(default_factory=dict)
    avg_score: float = 0.0
    max_level: RiskLevel = RiskLevel.LOW

    @property
    def no_travel_mi(self) -> float:
        return self.miles_by_level.get(RiskLevel.NO_TRAVEL, 0.0)

    @property
    def severe_mi(self) -> float:
        """Severe-or-worse miles (No Travel is strictly worse than Severe)."""
        return self.miles_by_level.get(RiskLevel.SEVERE, 0.0) + self.no_travel_mi

    @property
    def high_mi(self) -> float:
        return self.miles_by_level.get(RiskLevel.HIGH, 0.0)

    def to_dict(self) -> dict:
        return {
            "miles_by_level": {lvl.key: round(self.miles_by_level.get(lvl, 0.0), 1) for lvl in RiskLevel},
            "no_travel_mi": round(self.no_travel_mi, 1),
            "severe_mi": round(self.severe_mi, 1),
            "high_mi": round(self.high_mi, 1),
            "avg_score": round(self.avg_score, 3),
            "max_level": self.max_level.key,
        }


def aggregate_risk(checkpoints: list[Checkpoint]) -> RouteRisk:
    """Distance-weighted risk: each checkpoint's level applies to the miles it covers."""
    miles = {lvl: 0.0 for lvl in RiskLevel}
    weighted = 0.0
    total = 0.0
    worst = RiskLevel.LOW
    for cp in checkpoints:
        if cp.risk is None:
            continue
        lvl = cp.risk.level
        miles[lvl] += cp.covered_mi
        weighted += int(lvl) * cp.covered_mi
        total += cp.covered_mi
        worst = max(worst, lvl)
    return RouteRisk(miles, weighted / total if total else 0.0, worst)
