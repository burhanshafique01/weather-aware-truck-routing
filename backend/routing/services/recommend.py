"""Route scoring and recommendation.

The assessment's preference order, applied in turn:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest travel time

"No Travel" is the band above Severe, so No Travel miles are compared first:
a route the driver cannot safely finish should never win because it happens
to have fewer *Severe* miles than one that is merely Severe.

Average risk is compared with a small tolerance. Without it, a route that is
hours slower can win on a difference like 0.023 vs 0.025 — usually just
because it is longer, which dilutes the same few Moderate miles. Within the
tolerance the two routes count as equally risky and travel time decides.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cmp_to_key

from .risk import Risk

# Miles are rounded before comparison so that floating-point noise in route
# geometry (e.g. 12.0000001 vs 12.0) never decides a recommendation.
MILE_PRECISION = 1
# Average risk is on the 0 (Low) – 4 (No Travel) scale; 0.05 is 1/20th of a band.
AVERAGE_RISK_TOLERANCE = 0.05


@dataclass(frozen=True)
class RouteMetrics:
    miles_by_level: dict[int, float]
    average_risk: float
    duration_s: float

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level.get(int(Risk.NO_TRAVEL), 0.0)

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level.get(int(Risk.SEVERE), 0.0)

    @property
    def high_miles(self) -> float:
        return self.miles_by_level.get(int(Risk.HIGH), 0.0)

    def exposure(self) -> tuple[float, float, float]:
        return (
            round(self.no_travel_miles, MILE_PRECISION),
            round(self.severe_miles, MILE_PRECISION),
            round(self.high_miles, MILE_PRECISION),
        )


def compute_metrics(levels: Sequence[int], coverage_mi: Sequence[float], duration_s: float) -> RouteMetrics:
    """Aggregate per-checkpoint risk into per-route metrics.

    ``coverage_mi[i]`` is how many road miles checkpoint ``i`` represents, so
    the average is distance-weighted rather than per-sample.
    """
    miles = {int(level): 0.0 for level in Risk}
    for level, mi in zip(levels, coverage_mi, strict=False):
        miles[int(level)] += mi
    total = sum(coverage_mi)
    average = sum(level * mi for level, mi in zip(levels, coverage_mi, strict=False)) / total if total else 0.0
    return RouteMetrics(miles_by_level=miles, average_risk=average, duration_s=duration_s)


def compare(a: RouteMetrics, b: RouteMetrics) -> int:
    """Negative if ``a`` is the better route, positive if ``b`` is, 0 if equal."""
    if a.exposure() != b.exposure():
        return -1 if a.exposure() < b.exposure() else 1
    if abs(a.average_risk - b.average_risk) > AVERAGE_RISK_TOLERANCE:
        return -1 if a.average_risk < b.average_risk else 1
    return (a.duration_s > b.duration_s) - (a.duration_s < b.duration_s)


def rank_routes(metrics: Sequence[RouteMetrics]) -> list[int]:
    """Indices of routes from best to worst (ties keep the router's order)."""
    return sorted(range(len(metrics)), key=cmp_to_key(lambda i, j: compare(metrics[i], metrics[j]) or i - j))


def explain(best: RouteMetrics, runner_up: RouteMetrics | None) -> str:
    """One human sentence on why the winner beat the next-best route."""
    if runner_up is None:
        return "Only one route was available."
    mile_criteria = [
        ("No Travel", best.no_travel_miles, runner_up.no_travel_miles),
        ("Severe", best.severe_miles, runner_up.severe_miles),
        ("High", best.high_miles, runner_up.high_miles),
    ]
    for name, a, b in mile_criteria:
        if round(a, MILE_PRECISION) != round(b, MILE_PRECISION):
            return f"Fewest {name} miles ({a:.1f} mi vs {b:.1f} mi on the next option)"
    if abs(best.average_risk - runner_up.average_risk) > AVERAGE_RISK_TOLERANCE:
        return (
            f"Same High/Severe exposure, lower average risk "
            f"({best.average_risk:.2f} vs {runner_up.average_risk:.2f})"
        )
    saved_min = (runner_up.duration_s - best.duration_s) / 60
    if saved_min >= 1:
        return f"Same weather exposure as the next option, and {saved_min:.0f} min faster"
    return "Same weather exposure and travel time as the next option"
