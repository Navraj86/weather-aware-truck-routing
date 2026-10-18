"""Route recommendation.

Routes are ranked lexicographically by:
  0. fewest No Travel miles (safety guard: a No Travel stretch is never preferable)
  1. fewest Severe miles (Severe + No Travel)
  2. fewest High miles
  3. lowest distance-weighted average risk score (Low=0 ... No Travel=4)
  4. shortest travel time (wall-clock, including HOS stops when enabled)

Miles are compared at 0.1 mi precision and the average at 0.01 so float noise
never outweighs a real difference further down the list.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checkpoints import RouteRisk


@dataclass(frozen=True)
class Candidate:
    route_id: str
    risk: RouteRisk
    travel_s: float


CRITERIA = ("no_travel", "severe", "high", "avg_risk", "time")


def sort_key(c: Candidate) -> tuple:
    return (
        round(c.risk.no_travel_mi, 1),
        round(c.risk.severe_mi, 1),
        round(c.risk.high_mi, 1),
        round(c.risk.avg_score, 2),
        round(c.travel_s),
    )


def _fmt_duration(seconds: float) -> str:
    minutes = round(abs(seconds) / 60)
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _compare(best: Candidate, other: Candidate) -> str:
    kb, ko = sort_key(best), sort_key(other)
    for name, vb, vo in zip(CRITERIA, kb, ko):
        if vb == vo:
            continue
        if name == "no_travel":
            return f"avoids {vo - vb:.0f} more No Travel miles"
        if name == "severe":
            return f"{vo - vb:.0f} fewer Severe miles"
        if name == "high":
            return f"{vo - vb:.0f} fewer High-risk miles"
        if name == "avg_risk":
            return f"lower average risk ({vb:.2f} vs {vo:.2f})"
        return f"same risk profile, {_fmt_duration(vo - vb)} faster"
    return "identical risk and travel time"


def recommend(candidates: list[Candidate]) -> dict:
    if not candidates:
        raise ValueError("No routes to rank")
    ranked = sorted(candidates, key=sort_key)
    best = ranked[0]
    reasons = [{"route_id": o.route_id, "reason": _compare(best, o)} for o in ranked[1:]]

    warnings = []
    if best.risk.no_travel_mi > 0:
        warnings.append(
            "Every route crosses No Travel conditions at this departure time. "
            "Consider delaying departure or reducing load."
        )
    elif best.risk.severe_mi > 0:
        warnings.append("Even the recommended route includes Severe conditions. Drive with extreme caution.")

    return {
        "route_id": best.route_id,
        "ranking": [c.route_id for c in ranked],
        "versus": reasons,
        "warnings": warnings,
        "criteria": [
            "Fewest No Travel miles",
            "Fewest Severe miles",
            "Fewest High miles",
            "Lowest average risk",
            "Shortest travel time",
        ],
    }
