"""Weather risk classification, exactly as specified in the assessment.

Thresholds (lower bound inclusive unless the spec says ">"):

    Condition  Low        Moderate    High        Severe      No Travel
    Wind       <25 mph    25-34       35-44       45-54       >=55 mph
    Rain       <0.10 in/h 0.10-0.25   0.25-0.50   0.50-1.00   >1.00
    Snow       <0.5 in/h  0.5-1.0     1.0-2.0     2.0-3.0     >3.0

Shared boundaries (e.g. rain 0.25) belong to the higher band, except the top
band which starts strictly above 1.00 in/h rain / 3.0 in/h snow. Wind bands are
written as whole mph, so 34.x mph is still Moderate and 35.0 is High.

Load rules (applied on top of the weather bands):
    wind >= 55 mph                     -> No Travel for any load
    wind 45-54 mph and load > 30,000 lb -> No Travel
    wind 35-44 mph and load > 40,000 lb -> Severe

The checkpoint level is the worst of all applicable rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }[self]

    @property
    def key(self) -> str:
        return self.name.lower()


def wind_level(mph: float) -> RiskLevel:
    if mph >= 55:
        return RiskLevel.NO_TRAVEL
    if mph >= 45:
        return RiskLevel.SEVERE
    if mph >= 35:
        return RiskLevel.HIGH
    if mph >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def rain_level(in_per_hr: float) -> RiskLevel:
    if in_per_hr > 1.00:
        return RiskLevel.NO_TRAVEL
    if in_per_hr >= 0.50:
        return RiskLevel.SEVERE
    if in_per_hr >= 0.25:
        return RiskLevel.HIGH
    if in_per_hr >= 0.10:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def snow_level(in_per_hr: float) -> RiskLevel:
    if in_per_hr > 3.0:
        return RiskLevel.NO_TRAVEL
    if in_per_hr >= 2.0:
        return RiskLevel.SEVERE
    if in_per_hr >= 1.0:
        return RiskLevel.HIGH
    if in_per_hr >= 0.5:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def load_wind_level(mph: float, load_lb: float) -> RiskLevel:
    """Extra wind risk for heavy loads; LOW means the load rules add nothing."""
    if mph >= 55:
        return RiskLevel.NO_TRAVEL
    if mph >= 45 and load_lb > 30_000:
        return RiskLevel.NO_TRAVEL
    if mph >= 35 and load_lb > 40_000:
        return RiskLevel.SEVERE
    return RiskLevel.LOW


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    load: RiskLevel
    drivers: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "level": self.level.key,
            "label": self.level.label,
            "score": int(self.level),
            "components": {
                "wind": self.wind.key,
                "rain": self.rain.key,
                "snow": self.snow.key,
                "load": self.load.key,
            },
            "drivers": list(self.drivers),
        }


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> RiskAssessment:
    wind = wind_level(wind_mph)
    rain = rain_level(rain_in_hr)
    snow = snow_level(snow_in_hr)
    load = load_wind_level(wind_mph, load_lb)
    level = max(wind, rain, snow, load)

    drivers: list[str] = []
    if level > RiskLevel.LOW:
        if wind == level:
            drivers.append(f"Wind {wind_mph:.0f} mph")
        if rain == level:
            drivers.append(f"Rain {rain_in_hr:.2f} in/hr")
        if snow == level:
            drivers.append(f"Snow {snow_in_hr:.2f} in/hr")
        if load == level and load > wind:
            drivers.append(f"Wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load")
    return RiskAssessment(level, wind, rain, snow, load, tuple(drivers))
