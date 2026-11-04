"""Hourly forecasts from Open-Meteo, batched, cached and time-interpolated.

Open-Meteo accepts many coordinates per request, so checkpoints for all
routes plus the heatmap grid are fetched together in a few calls. Values are
linearly interpolated between forecast hours so a checkpoint reached at 14:40
gets weather for 14:40, not for 14:00 or 15:00.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests
from django.conf import settings
from django.core.cache import cache

from . import geo
from .http import ProviderError, session, timeout

log = logging.getLogger(__name__)

HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
BATCH_SIZE = 50
COORD_PRECISION = 2  # cache/dedupe key precision (~0.7 mi)


@dataclass(frozen=True)
class Conditions:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float

    def as_dict(self) -> dict:
        return {
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 3),
        }


@dataclass(frozen=True)
class HourlySeries:
    start: datetime  # UTC, on the hour
    wind: tuple[float, ...]
    gust: tuple[float, ...]
    rain: tuple[float, ...]  # rain + convective showers, in/hr
    snow: tuple[float, ...]  # snowfall, in/hr

    def at(self, when: datetime) -> Conditions:
        hours = (when - self.start).total_seconds() / 3600
        last = len(self.wind) - 1
        if hours <= 0:
            i, frac = 0, 0.0
        elif hours >= last:
            i, frac = last, 0.0
        else:
            i = int(hours)
            frac = hours - i

        def lerp(series: tuple[float, ...]) -> float:
            if frac == 0.0:
                return series[i]
            return series[i] + (series[i + 1] - series[i]) * frac

        return Conditions(lerp(self.wind), lerp(self.gust), lerp(self.rain), lerp(self.snow))


def hour_floor(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def hour_ceil(dt: datetime) -> datetime:
    floored = hour_floor(dt)
    return floored if floored == dt.astimezone(UTC) else floored + timedelta(hours=1)


def key_for(point: geo.LatLon) -> tuple[float, float]:
    return round(point[0], COORD_PRECISION), round(point[1], COORD_PRECISION)


def fetch_series(points: list[geo.LatLon], start: datetime, end: datetime) -> dict[tuple[float, float], HourlySeries]:
    """Hourly series for every point, keyed by ``key_for(point)``."""
    start, end = hour_floor(start), hour_ceil(end)
    window = f"{start:%Y%m%d%H}-{end:%Y%m%d%H}"
    unique = list(dict.fromkeys(key_for(p) for p in points))

    results: dict[tuple[float, float], HourlySeries] = {}
    missing: list[tuple[float, float]] = []
    cached = cache.get_many([_cache_key(k, window) for k in unique])
    for k in unique:
        hit = cached.get(_cache_key(k, window))
        if hit is None:
            missing.append(k)
        else:
            results[k] = hit

    batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    if batches:
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
            for batch, series in zip(batches, pool.map(lambda b: _fetch_batch(b, start, end), batches), strict=False):
                fresh = dict(zip(batch, series, strict=False))
                results.update(fresh)
                cache.set_many(
                    {_cache_key(k, window): v for k, v in fresh.items()},
                    timeout=settings.WEATHER_CACHE_SECONDS,
                )
    log.info(
        "weather: %d points, %d cached, %d fetched in %d calls",
        len(unique),
        len(unique) - len(missing),
        len(missing),
        len(batches),
    )
    return results


def _cache_key(k: tuple[float, float], window: str) -> str:
    return f"wx:{k[0]:.{COORD_PRECISION}f}:{k[1]:.{COORD_PRECISION}f}:{window}"


def _fetch_batch(batch: list[tuple[float, float]], start: datetime, end: datetime) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{lat:.{COORD_PRECISION}f}" for lat, _ in batch),
        "longitude": ",".join(f"{lon:.{COORD_PRECISION}f}" for _, lon in batch),
        "hourly": ",".join(HOURLY_VARIABLES),
        "start_hour": f"{start:%Y-%m-%dT%H:%M}",
        "end_hour": f"{end:%Y-%m-%dT%H:%M}",
        "timezone": "GMT",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
    }
    base = settings.OPEN_METEO_URL
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
        base = base.replace("://api.", "://customer-api.")
    try:
        resp = session().get(f"{base}/v1/forecast", params=params, timeout=timeout())
    except requests.RequestException as exc:
        log.warning("Open-Meteo unreachable: %s", exc)
        raise ProviderError("The weather service is unreachable. Please try again shortly.") from exc
    if resp.status_code == 429:
        raise ProviderError("The weather service rate limit was reached. Please wait a minute and retry.", status=503)
    if resp.status_code == 400:
        reason = resp.json().get("reason", "invalid request")
        raise ProviderError(f"Weather forecast unavailable for this time window ({reason}).", status=422)
    if not resp.ok:
        raise ProviderError(f"The weather service returned an error ({resp.status_code}).")

    payload = resp.json()
    locations = payload if isinstance(payload, list) else [payload]
    if len(locations) != len(batch):
        raise ProviderError("The weather service returned an unexpected response.")
    return [_parse(loc["hourly"], start) for loc in locations]


def _parse(hourly: dict, start: datetime) -> HourlySeries:
    def col(name: str) -> tuple[float, ...]:
        # Open-Meteo uses null for hours a model does not cover; treat as calm/dry.
        return tuple(float(v) if v is not None else 0.0 for v in hourly[name])

    rain = tuple(r + s for r, s in zip(col("rain"), col("showers"), strict=False))
    return HourlySeries(
        start=start,
        wind=col("wind_speed_10m"),
        gust=col("wind_gusts_10m"),
        rain=rain,
        snow=col("snowfall"),
    )
