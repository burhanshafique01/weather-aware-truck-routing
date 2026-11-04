"""Truck routing through a Valhalla server (OpenStreetMap data, truck costing).

Valhalla returns at most a couple of native alternates and sometimes none on
shorter trips. To always offer three meaningfully different options we add
detour candidates: the same trip forced *through* a point offset to either
side of the corridor, keeping only results that are distinct from the routes
we already have and not absurdly slower.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from django.conf import settings

from . import geo
from .http import ProviderError, session, timeout

log = logging.getLogger(__name__)

LB_PER_TONNE = 2204.62
# Empty tractor-trailer weight added to the load to get gross vehicle weight,
# which is what Valhalla's truck costing uses for weight restrictions.
TARE_WEIGHT_LB = 35_000

MAX_DURATION_RATIO = 1.6  # reject detours more than 60% slower than the fastest
MAX_OVERLAP = 0.85  # reject routes sharing more than 85% of their miles
OVERLAP_TOLERANCE_MI = 1.0


@dataclass
class RawRoute:
    coords: list[geo.LatLon]
    cum_mi: list[float]
    cum_s: list[float]
    distance_mi: float
    duration_s: float
    major_roads: list[str]
    source: str  # "primary", "alternate" or "detour"


def fetch_routes(origin: geo.LatLon, destination: geo.LatLon, load_lb: float, count: int = 3) -> list[RawRoute]:
    gross_tonnes = (load_lb + TARE_WEIGHT_LB) / LB_PER_TONNE
    if geo.haversine_mi(origin, destination) <= _max_leg_mi():
        trip = _request([origin, destination], gross_tonnes, alternates=count - 1)
        routes = [_parse_trip(trip["trip"], "primary")]
        routes += [_parse_trip(alt["trip"], "alternate") for alt in trip.get("alternates", [])]
        routes = _distinct(routes)
    else:
        # Too long for one request on this server: no native alternates.
        routes = [route_through([origin, destination], gross_tonnes, "primary")]

    if len(routes) < count:
        routes = _add_detours(routes, origin, destination, gross_tonnes, count)

    routes.sort(key=lambda r: r.duration_s)
    return routes[:count]


def _max_leg_mi() -> float:
    return settings.VALHALLA_MAX_LEG_KM / 1.609344


def route_through(points: list[geo.LatLon], gross_tonnes: float, source: str) -> RawRoute:
    """Route visiting ``points`` in order, split into requests the server accepts.

    The public Valhalla server rejects requests whose waypoints span more
    than ~1,500 km in straight-line distance. Long legs get intermediate
    waypoints on the great circle (with a generous snapping radius, so they
    land on a nearby highway), and waypoints are packed into as few requests
    as fit under the limit. The partial routes are then stitched together.
    """
    limit = _max_leg_mi()
    expanded = [points[0]]
    for a, b in zip(points, points[1:], strict=False):
        dist = geo.haversine_mi(a, b)
        pieces = max(1, math.ceil(dist / (limit * 0.95)))
        bearing = geo.initial_bearing(a, b)
        for k in range(1, pieces):
            expanded.append(geo.offset_point(a, bearing, dist * k / pieces))
        expanded.append(b)

    groups: list[list[geo.LatLon]] = [[expanded[0]]]
    span = 0.0
    for prev, cur in zip(expanded, expanded[1:], strict=False):
        step = geo.haversine_mi(prev, cur)
        if span + step > limit and len(groups[-1]) > 1:
            groups.append([prev])
            span = 0.0
        groups[-1].append(cur)
        span += step

    parts = [_parse_trip(_request(g, gross_tonnes)["trip"], source) for g in groups]
    return parts[0] if len(parts) == 1 else _stitch(parts, source)


def _stitch(parts: list[RawRoute], source: str) -> RawRoute:
    coords = list(parts[0].coords)
    cum_s = list(parts[0].cum_s)
    roads: Counter[str] = Counter()
    for p in parts[1:]:
        offset = cum_s[-1]
        coords.extend(p.coords[1:])
        cum_s.extend(t + offset for t in p.cum_s[1:])
    for p in parts:
        roads.update({name: len(parts) - i for i, name in enumerate(p.major_roads)})
    return RawRoute(
        coords=coords,
        cum_mi=geo.cumulative_miles(coords),
        cum_s=cum_s,
        distance_mi=sum(p.distance_mi for p in parts),
        duration_s=sum(p.duration_s for p in parts),
        major_roads=[n for n, _ in roads.most_common(3)],
        source=source,
    )


def _request(locations: list[geo.LatLon], gross_tonnes: float, alternates: int = 0) -> dict:
    last = len(locations) - 1
    body = {
        "locations": [
            {"lat": lat, "lon": lon, "type": "break"}
            if i in (0, last)
            # Waypoints we invented may sit off-road; let them snap to any road within 15 km.
            else {"lat": lat, "lon": lon, "type": "through", "radius": 15000}
            for i, (lat, lon) in enumerate(locations)
        ],
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(gross_tonnes, 2)}},
        "units": "miles",
        # Maneuvers (only returned with narrative on) carry the per-step times used for ETAs.
        "directions_options": {"units": "miles"},
        "alternates": alternates,
    }
    try:
        resp = session().post(f"{settings.VALHALLA_URL}/route", json=body, timeout=timeout())
    except requests.RequestException as exc:
        log.warning("Valhalla unreachable: %s", exc)
        raise ProviderError("The routing service is unreachable. Please try again shortly.") from exc
    if resp.status_code == 400:
        detail = _safe_json(resp).get("error", "No route found")
        raise ProviderError(f"No truck route found between these places ({detail}).", status=422)
    if not resp.ok:
        raise ProviderError(f"The routing service returned an error ({resp.status_code}).")
    return resp.json()


def _safe_json(resp: requests.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _parse_trip(trip: dict, source: str) -> RawRoute:
    """Flatten Valhalla legs into one line with elapsed seconds per vertex.

    Valhalla reports time per *maneuver*; we spread each maneuver's time over
    its shape vertices in proportion to distance, which gives an ETA for any
    point along the route.
    """
    coords: list[geo.LatLon] = []
    cum_s: list[float] = []
    roads: Counter[str] = Counter()
    elapsed = 0.0

    for leg in trip["legs"]:
        shape = geo.decode_polyline(leg["shape"], precision=6)
        seg_mi = [geo.haversine_mi(a, b) for a, b in zip(shape, shape[1:], strict=False)]
        vertex_time = [0.0] * len(shape)
        for m in leg["maneuvers"]:
            b, e = m["begin_shape_index"], m["end_shape_index"]
            span = sum(seg_mi[b:e])
            t = float(m.get("time", 0.0))
            for i in range(b, e):
                vertex_time[i + 1] += t * (seg_mi[i] / span) if span else t / max(e - b, 1)
            for name in m.get("street_names", [])[:1]:
                roads[name] += float(m.get("length", 0.0))

        start = 1 if coords else 0  # legs share their joining vertex
        for i in range(start, len(shape)):
            elapsed += vertex_time[i]
            coords.append(shape[i])
            cum_s.append(elapsed)

    cum_mi = geo.cumulative_miles(coords)
    summary = trip["summary"]
    return RawRoute(
        coords=coords,
        cum_mi=cum_mi,
        cum_s=cum_s,
        distance_mi=float(summary["length"]),
        duration_s=float(summary["time"]),
        major_roads=_major_roads(roads),
        source=source,
    )


_DIRECTION = re.compile(r"^(North|South|East|West)\s+|\s+(North|South|East|West|N|S|E|W)$")
_HIGHWAY = re.compile(r"^(I|US|SR|[A-Z]{2})[ -]?\d+[A-Z]?$")


def normalize_road(name: str) -> str:
    """'South Interstate 45' / 'I 45 South' -> 'I-45'; 'US 20' -> 'US-20'."""
    name = _DIRECTION.sub("", name.strip())
    name = re.sub(r"^Interstate\s+", "I ", name)
    return re.sub(r"^([A-Z]{1,2})\s+(\d)", r"\1-\2", name)


def _major_roads(roads: Counter[str], limit: int = 3) -> list[str]:
    merged: Counter[str] = Counter()
    for name, miles in roads.items():
        merged[normalize_road(name)] += miles
    ranked = [name for name, _ in merged.most_common()]
    highways = [n for n in ranked if _HIGHWAY.match(n)]
    return (highways or ranked)[:limit]


def _add_detours(
    routes: list[RawRoute], origin: geo.LatLon, destination: geo.LatLon, gross_tonnes: float, count: int
) -> list[RawRoute]:
    base = routes[0]
    straight_mi = geo.haversine_mi(origin, destination)
    mid, _, _ = geo.interpolate_along(base.coords, base.cum_mi, base.cum_mi[-1] / 2)
    bearing = geo.initial_bearing(origin, destination)

    candidates = []
    for fraction in (0.18, 0.32):
        offset = min(max(straight_mi * fraction, 8.0), 180.0)
        for side in (90, -90):
            candidates.append(geo.offset_point(mid, bearing + side, offset))

    def attempt(via: geo.LatLon) -> RawRoute | None:
        try:
            return route_through([origin, via, destination], gross_tonnes, "detour")
        except ProviderError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        detours = [r for r in pool.map(attempt, candidates) if r is not None]

    fastest = min(r.duration_s for r in routes)
    for detour in sorted(detours, key=lambda r: r.duration_s):
        if len(routes) >= count:
            break
        if detour.duration_s > fastest * MAX_DURATION_RATIO:
            continue
        if all(overlap_ratio(detour, r) < MAX_OVERLAP for r in routes):
            routes.append(detour)
    return routes


def _distinct(routes: list[RawRoute]) -> list[RawRoute]:
    kept: list[RawRoute] = []
    for r in routes:
        if all(overlap_ratio(r, k) < MAX_OVERLAP for k in kept):
            kept.append(r)
    return kept


def overlap_ratio(a: RawRoute, b: RawRoute, step_mi: float = 2.0) -> float:
    """Share of route ``a``'s miles that run along route ``b``.

    Uses a coarse spatial hash of ``b`` so the check stays fast on
    thousand-mile routes.
    """
    cell = 0.05  # degrees, ~3.5 mi: comfortably above the tolerance
    buckets: dict[tuple[int, int], list[geo.LatLon]] = {}
    for pt in geo.simplify_by_distance(b.coords, 0.25):
        buckets.setdefault((math.floor(pt[0] / cell), math.floor(pt[1] / cell)), []).append(pt)

    marks = geo.sample_distances(a.cum_mi[-1], step_mi)
    if not marks:
        return 1.0
    shared = 0
    for d in marks:
        pt, _, _ = geo.interpolate_along(a.coords, a.cum_mi, d)
        ci, cj = math.floor(pt[0] / cell), math.floor(pt[1] / cell)
        near = (q for di in (-1, 0, 1) for dj in (-1, 0, 1) for q in buckets.get((ci + di, cj + dj), ()))
        if any(geo.haversine_mi(pt, q) <= OVERLAP_TOLERANCE_MI for q in near):
            shared += 1
    return shared / len(marks)
