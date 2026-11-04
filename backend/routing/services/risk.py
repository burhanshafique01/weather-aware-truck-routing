"""Weather risk classification, exactly as specified in the assessment.

Bands are lower-bound inclusive: a value that sits on a shared boundary
(e.g. 0.25 in/hr of rain, listed in both Moderate and High) belongs to the
higher band. The top band for rain and snow starts *above* its threshold
(">1.00", ">3.0"), while wind's starts *at* it ("≥55 mph").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


# Lower bounds for Moderate, High, Severe. No Travel is handled separately
# because its inclusivity differs per condition.
WIND_BANDS_MPH = (25.0, 35.0, 45.0)
WIND_NO_TRAVEL_MPH = 55.0  # >= 55

RAIN_BANDS_IN_HR = (0.10, 0.25, 0.50)
RAIN_NO_TRAVEL_IN_HR = 1.00  # > 1.00

SNOW_BANDS_IN_HR = (0.5, 1.0, 2.0)
SNOW_NO_TRAVEL_IN_HR = 3.0  # > 3.0

# Load rules
HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # 45–54 mph wind with load > 30,000 lb
HEAVY_LOAD_SEVERE_LB = 40_000  # 35–44 mph wind with load > 40,000 lb


def _banded(value: float, bands: tuple[float, float, float]) -> Risk:
    moderate, high, severe = bands
    if value >= severe:
        return Risk.SEVERE
    if value >= high:
        return Risk.HIGH
    if value >= moderate:
        return Risk.MODERATE
    return Risk.LOW


def wind_risk(mph: float) -> Risk:
    if mph >= WIND_NO_TRAVEL_MPH:
        return Risk.NO_TRAVEL
    return _banded(mph, WIND_BANDS_MPH)


def rain_risk(in_hr: float) -> Risk:
    if in_hr > RAIN_NO_TRAVEL_IN_HR:
        return Risk.NO_TRAVEL
    return _banded(in_hr, RAIN_BANDS_IN_HR)


def snow_risk(in_hr: float) -> Risk:
    if in_hr > SNOW_NO_TRAVEL_IN_HR:
        return Risk.NO_TRAVEL
    return _banded(in_hr, SNOW_BANDS_IN_HR)


def apply_load_rules(wind: Risk, mph: float, load_lb: float) -> tuple[Risk, str | None]:
    """Escalate the wind risk for heavy loads. Returns (risk, reason or None)."""
    if wind == Risk.SEVERE and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return Risk.NO_TRAVEL, (f"Wind {mph:.0f} mph with a load over {HEAVY_LOAD_NO_TRAVEL_LB:,} lb")
    if wind == Risk.HIGH and load_lb > HEAVY_LOAD_SEVERE_LB:
        return Risk.SEVERE, f"Wind {mph:.0f} mph with a load over {HEAVY_LOAD_SEVERE_LB:,} lb"
    return wind, None


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "level": int(self.level),
            "label": self.level.label,
            "components": {
                "wind": int(self.wind),
                "rain": int(self.rain),
                "snow": int(self.snow),
            },
            "reasons": self.reasons,
        }


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk at one checkpoint: the worst of wind (load-adjusted), rain and snow."""
    base_wind = wind_risk(wind_mph)
    wind, load_reason = apply_load_rules(base_wind, wind_mph, load_lb)
    rain = rain_risk(rain_in_hr)
    snow = snow_risk(snow_in_hr)
    level = max(wind, rain, snow)

    reasons: list[str] = []
    if load_reason:
        reasons.append(f"{load_reason} → {wind.label}")
    if level > Risk.LOW:
        if wind == level and not load_reason:
            reasons.append(f"Wind {wind_mph:.0f} mph → {wind.label}")
        if rain == level:
            reasons.append(f"Rain {rain_in_hr:.2f} in/hr → {rain.label}")
        if snow == level:
            reasons.append(f"Snow {snow_in_hr:.2f} in/hr → {snow.label}")
    return Assessment(level=level, wind=wind, rain=rain, snow=snow, reasons=reasons)


def classify_level(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> int:
    """Fast path used for the heatmap grid, where reasons are not needed."""
    wind, _ = apply_load_rules(wind_risk(wind_mph), wind_mph, load_lb)
    return int(max(wind, rain_risk(rain_in_hr), snow_risk(snow_in_hr)))
