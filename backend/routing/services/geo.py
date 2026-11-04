"""Small, dependency-free geometry helpers for working with route polylines."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence

EARTH_RADIUS_MI = 3958.7613

LatLon = tuple[float, float]


def haversine_mi(a: LatLon, b: LatLon) -> float:
    """Great-circle distance between two (lat, lon) points in miles."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    coords: list[LatLon] = []
    factor = 10**precision
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / factor, lon / factor))
    return coords


def cumulative_miles(coords: Sequence[LatLon]) -> list[float]:
    """Running distance (miles) from the first coordinate to each coordinate."""
    totals = [0.0]
    for prev, cur in zip(coords, coords[1:], strict=False):
        totals.append(totals[-1] + haversine_mi(prev, cur))
    return totals


def interpolate_along(coords: Sequence[LatLon], cum: Sequence[float], target_mi: float) -> tuple[LatLon, int, float]:
    """Point at ``target_mi`` along the line.

    Returns the point, the index of the segment start and the fraction of the
    way along that segment, so callers can interpolate other per-vertex values
    (such as elapsed time) the same way.
    """
    if target_mi <= 0:
        return coords[0], 0, 0.0
    if target_mi >= cum[-1]:
        return coords[-1], len(coords) - 1, 0.0
    i = bisect.bisect_right(cum, target_mi) - 1
    seg = cum[i + 1] - cum[i]
    frac = 0.0 if seg == 0 else (target_mi - cum[i]) / seg
    (lat1, lon1), (lat2, lon2) = coords[i], coords[i + 1]
    return (lat1 + (lat2 - lat1) * frac, lon1 + (lon2 - lon1) * frac), i, frac


def sample_distances(total_mi: float, interval_mi: float) -> list[float]:
    """Distances 0, interval, 2*interval, ... plus the destination itself."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    marks = [0.0]
    d = interval_mi
    while d < total_mi - 1e-6:
        marks.append(d)
        d += interval_mi
    if total_mi > 0:
        marks.append(total_mi)
    return marks


def midpoint_coverage(marks: Sequence[float]) -> list[float]:
    """Miles of road each sample point is responsible for.

    Each checkpoint covers the stretch from the midpoint with its previous
    checkpoint to the midpoint with its next one, so the coverage always sums
    to the route length and no mile is counted twice.
    """
    n = len(marks)
    if n == 0:
        return []
    if n == 1:
        return [0.0]
    coverage = []
    for i in range(n):
        left = marks[i] if i == 0 else (marks[i - 1] + marks[i]) / 2
        right = marks[i] if i == n - 1 else (marks[i] + marks[i + 1]) / 2
        coverage.append(right - left)
    return coverage


def offset_point(origin: LatLon, bearing_deg: float, distance_mi: float) -> LatLon:
    """Point reached travelling ``distance_mi`` from origin on a bearing."""
    lat1 = math.radians(origin[0])
    lon1 = math.radians(origin[1])
    brg = math.radians(bearing_deg)
    d = distance_mi / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def initial_bearing(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def simplify_by_distance(coords: Sequence[LatLon], min_gap_mi: float) -> list[LatLon]:
    """Drop vertices closer than ``min_gap_mi`` to the last kept one.

    Keeps map payloads small without visibly changing the line.
    """
    if not coords:
        return []
    kept = [coords[0]]
    for pt in coords[1:-1]:
        if haversine_mi(kept[-1], pt) >= min_gap_mi:
            kept.append(pt)
    if len(coords) > 1:
        kept.append(coords[-1])
    return kept
