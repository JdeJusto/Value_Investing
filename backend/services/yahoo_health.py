"""Yahoo Finance availability preflight.

Yahoo is the only source of market data for Value Investing (prices are
fetched on demand and never persisted), and it fails in a way that is
expensive to discover late: the quote summary ``.info`` endpoint answers 404
for unknown symbols and 429/503 under throttling, and a burst of
universe-sized requests can be cut off mid-run. When Yahoo is unreachable,
every price-derived metric (P/E, P/B, FCF yield, EV/EBIT, margin of safety)
degrades to N/A, so a preflight turns a slow, confusing half-run into a
single clear skip: the fundamentals analysis still runs and the report says
why the market fields are empty.

:func:`check_yahoo_availability` probes a tiny chart request for AAPL — the
same host and endpoint family PriceService uses — with one retry (Yahoo is
intermittently slow without being down) and caches the result for 120 s
per process, mirroring the SEC preflight in
:mod:`backend.services.sec_health`.

The probe is injectable, so tests never touch the network, and no price is
read, stored or reported by this module.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Callable, Optional

logger = logging.getLogger("backend.yahoo_health")

# 1 day / 1d interval keeps the probe body tiny (a few KB) while proving that
# the chart endpoint this service depends on answers.
YAHOO_HEALTH_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d"
)

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_ATTEMPTS = 2  # one retry absorbs transient failures
DEFAULT_RETRY_DELAY_SECONDS = 0.5
DEFAULT_TTL_SECONDS = 120.0


@dataclass(frozen=True)
class YahooHealth:
    """Outcome of one Yahoo availability probe."""

    available: bool
    reason: str
    http_status: Optional[int] = None
    checked_at: float = 0.0


_cache: Optional[YahooHealth] = None
_cache_lock = threading.Lock()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def reset_yahoo_health_cache() -> None:
    """Drop the cached probe result (tests; ``force=True`` bypasses it too)."""
    global _cache
    with _cache_lock:
        _cache = None


def _probe(url: str, timeout: float) -> YahooHealth:
    """One GET request; any transport failure means unavailable."""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            # Yahoo answers 429 to requests without a browser-like agent.
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            # Drain a little so the connection is not left half-read.
            response.read(64)
            return YahooHealth(True, "ok", int(status), time.time())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return YahooHealth(
                False, "Yahoo returned HTTP 429 (rate limited)", exc.code, time.time()
            )
        if exc.code == 404:
            return YahooHealth(
                False, "Yahoo returned HTTP 404 (endpoint moved)", exc.code, time.time()
            )
        return YahooHealth(False, f"Yahoo returned HTTP {exc.code}", exc.code, time.time())
    except Exception as exc:  # noqa: BLE001 — any failure means unavailable
        return YahooHealth(False, f"Yahoo unreachable: {exc}", None, time.time())


def check_yahoo_availability(
    *,
    timeout: Optional[float] = None,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ttl: Optional[float] = None,
    force: bool = False,
    probe: Optional[Callable[[str, float], YahooHealth]] = None,
) -> YahooHealth:
    """Return (and cache) whether Yahoo Finance is reachable right now.

    - ``attempts`` tries (default 2: one retry spaced by ``retry_delay``).
    - The first result is cached for ``ttl`` seconds (default 120, env
      ``YAHOO_HEALTH_TTL_SECONDS``; timeout env ``YAHOO_HEALTH_TIMEOUT_SECONDS``)
      unless ``force=True``.
    - A probe that raises is reported as unavailable, never propagated.
    """
    global _cache

    timeout = (
        timeout
        if timeout is not None
        else _env_float("YAHOO_HEALTH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    )
    ttl = (
        ttl if ttl is not None else _env_float("YAHOO_HEALTH_TTL_SECONDS", DEFAULT_TTL_SECONDS)
    )
    probe_fn = probe or _probe

    with _cache_lock:
        cached = _cache
    if cached is not None and not force:
        if time.time() - cached.checked_at < ttl:
            return cached

    total = max(1, int(attempts))
    health = YahooHealth(False, "Yahoo availability unknown", None, time.time())
    for attempt in range(total):
        try:
            health = probe_fn(YAHOO_HEALTH_URL, timeout)
        except Exception as exc:  # noqa: BLE001 — a broken probe = unavailable
            health = YahooHealth(False, f"Yahoo preflight error: {exc}", None, time.time())
        if health.available:
            break
        if attempt + 1 < total:
            time.sleep(retry_delay)

    # The cache clock is owned here: probes need not set checked_at.
    health = replace(health, checked_at=time.time())
    with _cache_lock:
        _cache = health
    if not health.available:
        logger.warning("Yahoo preflight failed: %s", health.reason)
    else:
        logger.debug("Yahoo preflight ok (HTTP %s)", health.http_status)
    return health


def probe(**kwargs) -> bool:
    """Boolean shortcut used by the prices pipeline: True when Yahoo answers."""
    return check_yahoo_availability(**kwargs).available


def cached_yahoo_health() -> Optional[YahooHealth]:
    """The last probe result, without performing any HTTP call.

    Lets the price service short-circuit every remaining fetch of a run once a
    probe has established that Yahoo is unreachable (observed in production
    runs: Yahoo answers HTTP 429 under throttling). None means "not probed
    yet", which callers must treat as "keep trying".
    """
    with _cache_lock:
        return _cache
