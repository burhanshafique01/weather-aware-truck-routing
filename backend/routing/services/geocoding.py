"""Place search via Photon (OpenStreetMap), suitable for type-ahead."""

from __future__ import annotations

import hashlib

import requests
from django.conf import settings
from django.core.cache import cache

from .http import ProviderError, session, timeout

CACHE_SECONDS = 24 * 3600


def search(query: str, limit: int = 6) -> list[dict]:
    query = query.strip()
    if len(query) < 2:
        return []
    key = "geo:" + hashlib.sha1(f"{query.lower()}|{limit}".encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit

    try:
        resp = session().get(
            f"{settings.PHOTON_URL}/api/",
            params={"q": query, "limit": limit, "lang": "en"},
            timeout=timeout(),
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ProviderError("Place search is unavailable right now.") from exc

    results = []
    seen = set()
    for feature in resp.json().get("features", []):
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"]
        label = _label(props)
        if label in seen:
            continue
        seen.add(label)
        results.append({"label": label, "lat": round(lat, 6), "lon": round(lon, 6)})
    cache.set(key, results, CACHE_SECONDS)
    return results


def first(query: str) -> dict | None:
    results = search(query, limit=1)
    return results[0] if results else None


def _label(props: dict) -> str:
    parts = [props.get("name")]
    for field in ("city", "county", "state", "country"):
        value = props.get(field)
        if value and value not in parts:
            parts.append(value)
            if field == "state":
                break
    if props.get("country") and props.get("country") != "United States" and props["country"] not in parts:
        parts.append(props["country"])
    return ", ".join(p for p in parts if p)
