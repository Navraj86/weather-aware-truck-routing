from datetime import datetime, timezone

import pytest

from planner.domain.checkpoints import RouteRisk, aggregate_risk, build_checkpoints, checkpoint_distances
from planner.domain.geo import Polyline
from planner.domain.hos import HOUR, DriveClock
from planner.domain.recommend import Candidate, recommend
from planner.domain.risk import RiskLevel, assess

def approx(x):
    return pytest.approx(x, rel=1e-4)


DEPART = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def straight_line(miles: float, mph: float = 60.0) -> Polyline:
    # Along the equator one degree of longitude is ~69.09 miles.
    deg = miles / 69.0933
    pl = Polyline([(0.0, 0.0), (0.0, deg)])
    pl.cum_s = [0.0, pl.length_mi / mph * 3600]
    return pl


# ------------------------------------------------------------------ checkpoints


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_cover_the_whole_route_exactly_once(interval):
    line = straight_line(137)
    cps = build_checkpoints(line, interval, DEPART, DriveClock())
    assert cps[0].distance_mi == 0 and cps[-1].distance_mi == pytest.approx(line.length_mi)
    assert sum(cp.covered_mi for cp in cps) == pytest.approx(line.length_mi)
    gaps = [b.distance_mi - a.distance_mi for a, b in zip(cps, cps[1:-1])]
    assert all(g == pytest.approx(interval) for g in gaps)


def test_checkpoint_eta_follows_drive_time():
    line = straight_line(120, mph=60)
    cps = build_checkpoints(line, 25, DEPART, DriveClock())
    assert (cps[1].eta - DEPART).total_seconds() == pytest.approx(25 * 60, abs=1)
    assert (cps[-1].eta - DEPART).total_seconds() == pytest.approx(2 * HOUR, abs=1)


def test_destination_close_to_last_checkpoint_is_merged():
    assert checkpoint_distances(50.2, 25) == [0, 25, 50.2]
    assert checkpoint_distances(51, 25) == [0, 25, 50, 51]
    assert checkpoint_distances(5, 25) == [0, 5]


def test_aggregate_risk_is_distance_weighted():
    cps = build_checkpoints(straight_line(100), 25, DEPART, DriveClock())  # 0,25,50,75,100
    levels = [(5, 0, 0), (50, 0, 0), (40, 0, 0), (5, 0.6, 0), (5, 0, 0)]  # low, severe, high, severe, low
    for cp, (w, r, s) in zip(cps, levels):
        cp.risk = assess(w, r, s, 10_000)
    risk = aggregate_risk(cps)
    assert risk.severe_mi == approx(50)
    assert risk.high_mi == approx(25)
    assert risk.miles_by_level[RiskLevel.LOW] == approx(25)
    assert risk.avg_score == approx((3 * 50 + 2 * 25) / 100)
    assert risk.max_level == RiskLevel.SEVERE


# ------------------------------------------------------------------ hours of service


def test_hos_disabled_is_identity():
    assert DriveClock(False).elapsed_s(20 * HOUR) == 20 * HOUR
    assert DriveClock(False).stops(20 * HOUR) == []


@pytest.mark.parametrize(
    "drive_h, elapsed_h",
    [(0, 0), (8, 8), (9, 9.5), (11, 11.5), (12, 22.5), (19, 29.5), (20, 31), (22, 33), (23, 44)],
)
def test_hos_elapsed(drive_h, elapsed_h):
    assert DriveClock(True).elapsed_s(drive_h * HOUR) == pytest.approx(elapsed_h * HOUR)


def test_hos_stops():
    stops = DriveClock(True).stops(20 * HOUR)
    assert [(s.kind, s.drive_s / HOUR) for s in stops] == [("break", 8), ("rest", 11), ("break", 19)]


# ------------------------------------------------------------------ recommendation


def risk(no_travel=0.0, severe=0.0, high=0.0, avg=0.0) -> RouteRisk:
    return RouteRisk({RiskLevel.NO_TRAVEL: no_travel, RiskLevel.SEVERE: severe, RiskLevel.HIGH: high}, avg)


def test_fewest_severe_miles_beats_faster_route():
    rec = recommend([Candidate("A", risk(severe=20), 3600), Candidate("B", risk(severe=5, high=80), 7200)])
    assert rec["route_id"] == "B"
    assert rec["versus"][0]["reason"] == "15 fewer Severe miles"


def test_high_miles_break_severe_ties():
    rec = recommend([Candidate("A", risk(high=30), 3600), Candidate("B", risk(high=10), 5000)])
    assert rec["route_id"] == "B"


def test_average_risk_then_time():
    rec = recommend([Candidate("A", risk(avg=0.4), 3600), Candidate("B", risk(avg=0.2), 5000)])
    assert rec["route_id"] == "B"
    rec = recommend([Candidate("A", risk(avg=0.2), 5000), Candidate("B", risk(avg=0.2), 3600)])
    assert rec["route_id"] == "B"
    assert rec["versus"][0]["reason"] == "same risk profile, 23 min faster"


def test_no_travel_is_avoided_first_and_warned():
    rec = recommend([Candidate("A", risk(no_travel=5), 3600), Candidate("B", risk(severe=40), 3600)])
    assert rec["route_id"] == "B"
    assert rec["warnings"]
    rec = recommend([Candidate("A", risk(no_travel=5), 3600), Candidate("B", risk(no_travel=9), 3600)])
    assert rec["route_id"] == "A"
    assert "No Travel" in rec["warnings"][0]


def test_float_noise_does_not_override_travel_time():
    rec = recommend([Candidate("A", risk(avg=0.1001), 3600), Candidate("B", risk(avg=0.1004), 3000)])
    assert rec["route_id"] == "B"
