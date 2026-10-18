import pytest

from planner.domain.risk import RiskLevel as L
from planner.domain.risk import assess, load_wind_level, rain_level, snow_level, wind_level


@pytest.mark.parametrize(
    "mph, expected",
    [(0, L.LOW), (24.9, L.LOW), (25, L.MODERATE), (34.9, L.MODERATE), (35, L.HIGH), (44.9, L.HIGH),
     (45, L.SEVERE), (54.9, L.SEVERE), (55, L.NO_TRAVEL), (80, L.NO_TRAVEL)],
)
def test_wind_bands(mph, expected):
    assert wind_level(mph) == expected


@pytest.mark.parametrize(
    "rate, expected",
    [(0, L.LOW), (0.099, L.LOW), (0.10, L.MODERATE), (0.249, L.MODERATE), (0.25, L.HIGH), (0.499, L.HIGH),
     (0.50, L.SEVERE), (1.00, L.SEVERE), (1.001, L.NO_TRAVEL)],
)
def test_rain_bands(rate, expected):
    assert rain_level(rate) == expected


@pytest.mark.parametrize(
    "rate, expected",
    [(0, L.LOW), (0.49, L.LOW), (0.5, L.MODERATE), (0.99, L.MODERATE), (1.0, L.HIGH), (1.99, L.HIGH),
     (2.0, L.SEVERE), (3.0, L.SEVERE), (3.01, L.NO_TRAVEL)],
)
def test_snow_bands(rate, expected):
    assert snow_level(rate) == expected


@pytest.mark.parametrize(
    "mph, load, expected",
    [
        (55, 0, L.NO_TRAVEL),  # >= 55 mph: No Travel for any load
        (50, 30_000, L.LOW),  # exactly 30,000 lb is not "> 30,000"
        (50, 30_001, L.NO_TRAVEL),
        (40, 40_000, L.LOW),
        (40, 40_001, L.SEVERE),
        (44.9, 80_000, L.SEVERE),
        (34.9, 80_000, L.LOW),
    ],
)
def test_load_rules(mph, load, expected):
    assert load_wind_level(mph, load) == expected


def test_assess_takes_the_worst_rule():
    a = assess(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0, load_lb=45_000)
    assert a.wind == L.HIGH and a.rain == L.HIGH and a.load == L.SEVERE
    assert a.level == L.SEVERE
    assert a.drivers == ("Wind 40 mph with 45,000 lb load",)


def test_assess_light_load_in_strong_wind_is_only_severe():
    assert assess(50, 0, 0, 20_000).level == L.SEVERE
    assert assess(50, 0, 0, 35_000).level == L.NO_TRAVEL


def test_assess_calm_weather_has_no_drivers():
    a = assess(5, 0, 0, 80_000)
    assert a.level == L.LOW and a.drivers == ()
    assert a.to_dict()["label"] == "Low"
