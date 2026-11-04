"""Trip planning: routes → timed checkpoints → weather → risk → recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from . import geo, heatmap, recommend, valhalla, weather
from .risk import Risk, assess, classify_level

HEATMAP_HOURS = 48
ROUTE_LETTERS = "ABCDEFGH"
PATH_SIMPLIFY_MI = 0.3


@dataclass(frozen=True)
class TripRequest:
    origin: geo.LatLon
    destination: geo.LatLon
    origin_label: str
    destination_label: str
    departure: datetime
    load_lb: float
    interval_mi: int


def plan_trip(req: TripRequest) -> dict:
    raw_routes = valhalla.fetch_routes(req.origin, req.destination, req.load_lb)
    departure = req.departure.astimezone(UTC)

    # 1. Checkpoints with ETAs, before any weather is fetched.
    route_checkpoints = [_checkpoints(r, departure, req.interval_mi) for r in raw_routes]

    # 2. Heatmap grid around every candidate route.
    grid = heatmap.corridor_grid([(r.coords, r.cum_mi) for r in raw_routes])

    # 3. One batched weather fetch covering the whole trip and the 48 h slider.
    last_eta = max(cp["eta"] for cps in route_checkpoints for cp in cps)
    window_end = max(last_eta, departure + timedelta(hours=HEATMAP_HOURS))
    points = [cp["point"] for cps in route_checkpoints for cp in cps] + grid.cells
    series = weather.fetch_series(points, departure, window_end)

    # 4. Risk per checkpoint and per-route metrics.
    routes_out = []
    metrics = []
    for idx, (raw, cps) in enumerate(zip(raw_routes, route_checkpoints, strict=False)):
        checkpoints_out, levels = [], []
        for n, cp in enumerate(cps):
            cond = series[weather.key_for(cp["point"])].at(cp["eta"])
            risk = assess(cond.wind_mph, cond.rain_in_hr, cond.snow_in_hr, req.load_lb)
            levels.append(int(risk.level))
            checkpoints_out.append(
                {
                    "index": n,
                    "mile": round(cp["mile"], 1),
                    "lat": round(cp["point"][0], 5),
                    "lon": round(cp["point"][1], 5),
                    "eta": _iso(cp["eta"]),
                    "coverage_mi": round(cp["coverage_mi"], 2),
                    "weather": cond.as_dict(),
                    "risk": risk.as_dict(),
                }
            )
        m = recommend.compute_metrics(levels, [cp["coverage_mi"] for cp in cps], raw.duration_s)
        metrics.append(m)
        routes_out.append(_route_payload(idx, raw, departure, checkpoints_out, m))

    # 5. Recommendation.
    order = recommend.rank_routes(metrics)
    best = order[0]
    runner_up = order[1] if len(order) > 1 else None
    for rank, i in enumerate(order, start=1):
        routes_out[i]["rank"] = rank
        routes_out[i]["recommended"] = i == best
    routes_out[best]["reason"] = recommend.explain(metrics[best], metrics[runner_up] if runner_up is not None else None)

    return {
        "request": {
            "origin": {"label": req.origin_label, "lat": req.origin[0], "lon": req.origin[1]},
            "destination": {"label": req.destination_label, "lat": req.destination[0], "lon": req.destination[1]},
            "departure": _iso(departure),
            "load_lb": req.load_lb,
            "interval_mi": req.interval_mi,
        },
        "generated_at": _iso(datetime.now(UTC)),
        "recommended_route_id": routes_out[best]["id"],
        "routes": routes_out,
        "heatmap": _heatmap_payload(grid, series, departure, req.load_lb),
        "risk_levels": [{"level": int(r), "label": r.label} for r in Risk],
    }


def _checkpoints(route: valhalla.RawRoute, departure: datetime, interval_mi: int) -> list[dict]:
    total = route.cum_mi[-1]
    marks = geo.sample_distances(total, interval_mi)
    coverage = geo.midpoint_coverage(marks)
    # Geometry miles can differ slightly from the router's reported distance;
    # scale so per-level miles add up to the distance shown to the user.
    scale = route.distance_mi / total if total else 1.0
    out = []
    for mark, cov in zip(marks, coverage, strict=False):
        point, i, frac = geo.interpolate_along(route.coords, route.cum_mi, mark)
        elapsed = route.cum_s[i] + (route.cum_s[min(i + 1, len(route.cum_s) - 1)] - route.cum_s[i]) * frac
        out.append(
            {
                "mile": mark * scale,
                "point": point,
                "eta": departure + timedelta(seconds=elapsed),
                "coverage_mi": cov * scale,
            }
        )
    return out


def _route_payload(
    idx: int, raw: valhalla.RawRoute, departure: datetime, checkpoints: list[dict], m: recommend.RouteMetrics
) -> dict:
    # ~1,500 vertices per route is visually lossless at any zoom a whole trip is viewed at.
    min_gap = max(PATH_SIMPLIFY_MI, raw.distance_mi / 1500)
    path = []
    last = None
    for (lat, lon), t in zip(raw.coords, raw.cum_s, strict=False):
        if last is None or geo.haversine_mi(last, (lat, lon)) >= min_gap:
            path.append([round(lat, 5), round(lon, 5), round(t)])
            last = (lat, lon)
    end_lat, end_lon = raw.coords[-1]
    if path[-1][:2] != [round(end_lat, 5), round(end_lon, 5)]:
        path.append([round(end_lat, 5), round(end_lon, 5), round(raw.cum_s[-1])])

    letter = ROUTE_LETTERS[idx]
    return {
        "id": letter,
        "name": f"Route {letter}",
        "via": raw.major_roads,
        "source": raw.source,
        "distance_mi": round(raw.distance_mi, 1),
        "duration_s": round(raw.duration_s),
        "arrival": _iso(departure + timedelta(seconds=raw.duration_s)),
        "metrics": {
            "miles_by_level": {Risk(k).name.lower(): round(v, 1) for k, v in m.miles_by_level.items()},
            "average_risk": round(m.average_risk, 3),
            "max_level": max((cp["risk"]["level"] for cp in checkpoints), default=0),
        },
        "rank": None,
        "recommended": False,
        "reason": None,
        "path": path,
        "checkpoints": checkpoints,
    }


def _heatmap_payload(grid: heatmap.Grid, series: dict, departure: datetime, load_lb: float) -> dict:
    """Per-cell, per-hour risk and conditions for the 0–48 h slider.

    Levels are encoded as one digit per hour ("0012…") to keep the payload
    compact; raw values are included so the map can show what drives a cell.
    """
    cells = []
    for lat, lon in grid.cells:
        s = series[weather.key_for((lat, lon))]
        levels, wind, rain, snow = [], [], [], []
        for h in range(HEATMAP_HOURS + 1):
            c = s.at(departure + timedelta(hours=h))
            levels.append(str(classify_level(c.wind_mph, c.rain_in_hr, c.snow_in_hr, load_lb)))
            wind.append(round(c.wind_mph))
            rain.append(round(c.rain_in_hr, 2))
            snow.append(round(c.snow_in_hr, 2))
        cells.append(
            {
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "levels": "".join(levels),
                "wind": wind,
                "rain": rain,
                "snow": snow,
            }
        )
    return {
        "start": _iso(departure),
        "hours": HEATMAP_HOURS,
        "dlat": round(grid.dlat, 5),
        "dlon": round(grid.dlon, 5),
        "cells": cells,
    }


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
