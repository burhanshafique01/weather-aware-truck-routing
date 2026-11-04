"""Shared HTTP session with sensible retries for third-party providers."""

from __future__ import annotations

import threading

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ProviderError(Exception):
    """A third-party provider failed or rejected the request.

    ``user_message`` is safe to show in the UI; ``status`` is the HTTP status
    the API should answer with.
    """

    def __init__(self, user_message: str, status: int = 502):
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


_local = threading.local()


def session() -> requests.Session:
    """One pooled session per thread (requests.Session is not thread-safe)."""
    s = getattr(_local, "session", None)
    if s is None:
        retry = Retry(
            total=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.headers["User-Agent"] = settings.HTTP_USER_AGENT
        _local.session = s
    return s


def timeout() -> float:
    return settings.HTTP_TIMEOUT_SECONDS
