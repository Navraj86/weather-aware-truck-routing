from __future__ import annotations

import threading
import time

import requests
from django.conf import settings


class UpstreamError(Exception):
    """A third-party API (routing, weather, geocoding) failed or rejected the request."""

    def __init__(self, service: str, message: str, status: int = 502):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message
        self.status = status


_local = threading.local()


def session() -> requests.Session:
    """One pooled session per thread (requests.Session is not guaranteed thread-safe)."""
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = settings.HTTP_USER_AGENT
        _local.session = s
    return s


RETRY_DELAYS_S = (1.5, 4.0)


def get_json(service: str, url: str, *, params=None, timeout: float = 25.0, retries: int = 0):
    """GET JSON, retrying dropped connections, timeouts, 429 and 5xx with backoff."""
    for attempt in range(retries + 1):
        last = attempt == retries
        try:
            resp = session().get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            if last:
                raise UpstreamError(service, f"request failed ({exc.__class__.__name__})") from exc
        else:
            if last or (resp.status_code != 429 and resp.status_code < 500):
                return _decode(service, resp)
        time.sleep(RETRY_DELAYS_S[min(attempt, len(RETRY_DELAYS_S) - 1)])
    raise AssertionError("unreachable")


def post_json(service: str, url: str, payload: dict, *, timeout: float = 30.0):
    try:
        resp = session().post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise UpstreamError(service, f"request failed ({exc.__class__.__name__})") from exc
    return _decode(service, resp)


def _decode(service: str, resp: requests.Response):
    if resp.status_code == 429:
        raise UpstreamError(service, "rate limit reached, please retry in a minute", 503)
    try:
        data = resp.json()
    except ValueError as exc:
        raise UpstreamError(service, f"invalid response (HTTP {resp.status_code})") from exc
    if resp.status_code >= 400:
        reason = data.get("reason") or data.get("error") or data.get("message") if isinstance(data, dict) else None
        raise UpstreamError(service, str(reason or f"HTTP {resp.status_code}"), 502)
    return data
