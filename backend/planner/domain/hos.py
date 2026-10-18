"""Converts pure driving time into wall-clock elapsed time.

When hours-of-service (HOS) is enabled we apply a simplified version of the
FMCSA property-carrying rules: a 30-minute break after 8 hours of driving and a
10-hour off-duty rest after 11 hours of driving. The 14-hour window and the
60/70-hour cycle are ignored. When HOS is disabled, elapsed == driving time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

HOUR = 3600.0
DRIVE_LIMIT_S = 11 * HOUR
BREAK_AFTER_S = 8 * HOUR
BREAK_S = 0.5 * HOUR
REST_S = 10 * HOUR


@dataclass(frozen=True)
class Stop:
    kind: str  # "break" | "rest"
    drive_s: float  # cumulative driving seconds when the stop begins
    duration_s: float


@dataclass(frozen=True)
class DriveClock:
    hos: bool = False

    def elapsed_s(self, drive_s: float) -> float:
        if not self.hos or drive_s <= 0:
            return max(drive_s, 0.0)
        # A stop scheduled exactly at arrival is not taken, hence ceil(...) - 1.
        rests = math.ceil(drive_s / DRIVE_LIMIT_S) - 1
        within = drive_s - rests * DRIVE_LIMIT_S
        extra = rests * (REST_S + BREAK_S)
        if within > BREAK_AFTER_S:
            extra += BREAK_S
        return drive_s + extra

    def stops(self, total_drive_s: float) -> list[Stop]:
        if not self.hos:
            return []
        out: list[Stop] = []
        period_start = 0.0
        while period_start < total_drive_s:
            if period_start + BREAK_AFTER_S < total_drive_s:
                out.append(Stop("break", period_start + BREAK_AFTER_S, BREAK_S))
            if period_start + DRIVE_LIMIT_S < total_drive_s:
                out.append(Stop("rest", period_start + DRIVE_LIMIT_S, REST_S))
            period_start += DRIVE_LIMIT_S
        return out
