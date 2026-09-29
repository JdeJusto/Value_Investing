"""SEC EDGAR availability preflight.

SEC's fair-access rules answer HTTP 403 to requests with a missing or
non-compliant User-Agent and to IPs that exceeded the request-rate guidance,
and the API can time out during incidents. Before the refresh step spawns
targeted ``sec sync`` subprocesses, :func:`check_sec_availability` probes a
tiny SEC endpoint (HEAD on the companyfacts API — the same host the
ingestion pipeline uses) so an unavailable SEC becomes a clear, single skip:
analysis continues with the fundamentals already stored in
Financial-DataBase instead of launching a burst of doomed syncs.

The probe result is cached per process (default 120 s) because commands are
usually run in short succession and SEC availability does not change
second-to-second. Nothing here reads or writes any database, and prices
never depend on it (they come from Yahoo through PriceService).

Note on provenance: Financial-DataBase's ``import_runs.status`` CHECK only
allows running/success/failed/partial, so no synthetic row is written for a
refresh that never started — the skip is recorded in the command log, the
refresh summary and ``RefreshResult.sec_skipped_reason`` instead.

Diagnosis and operational notes: Financial-DataBase
``docs/sec_403_investigation.md``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace

logger = logging.getLogger("backend.sec_health")

# AAPL's companyfacts file: same host and endpoint family the SEC ingestion
# uses, and HEAD keeps the probe bodyless (a few hundred bytes).
SEC_HEALTH_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"

DEFAULT_TIMEOUT_SECONDS = 6.0
DEFAULT_ATTEMPTS = 2  # one retry absorbs transient failures
DEFAULT_RETRY_DELAY_SECONDS = 0.5
DEFAULT_TTL_SECONDS = 120.0


@dataclass(frozen=True)
class SecHealth:
    """Outcome of one SEC availability probe."""

    available: bool
    reason: str
    http_status: int | None = None
    checked_at: float = 0.0


_cache: SecHealth | None = None
_cache_lock = threading.Lock()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def reset_sec_health_cache() -> None:
    """Drop the cached probe result (tests; ``force=True`` bypasses it too)."""
    global _cache
    with _cache_lock:
        _cache = None


def _probe(url: str, user_agent: str, timeout: float) -> SecHealth:
    """One HEAD request; any transport failure means unavailable."""
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            return SecHealth(True, "ok", int(status), time.time())
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return SecHealth(
                False,
                "SEC returned HTTP 403 (rate limit or non-compliant User-Agent)",
                exc.code,
                time.time(),
            )
        return SecHealth(False, f"SEC returned HTTP {exc.code}", exc.code, time.time())
    except Exception as exc:  # noqa: BLE001 — any failure means unavailable
        return SecHealth(False, f"SEC unreachable: {exc}", None, time.time())


def check_sec_availability(
    *,
    timeout: float | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ttl: float | None = None,
    force: bool = False,
    probe: Callable[[str, str, float], SecHealth] | None = None,
) -> SecHealth:
    """Return (and cache) whether SEC EDGAR is reachable right now.

    - Missing ``SEC_USER_AGENT``: unavailable, without any HTTP call (the
      ingestion refuses to run without it, so the refresh would fail anyway).
    - Otherwise a HEAD probe of :data:`SEC_HEALTH_URL` with ``attempts``
      tries (default 2: one retry spaced by ``retry_delay``) — SEC can be
      intermittently slow without being down.
    - The first result is cached for ``ttl`` seconds (default 120, env
      ``SEC_HEALTH_TTL_SECONDS``; timeout env ``SEC_HEALTH_TIMEOUT_SECONDS``)
      unless ``force=True``.
    """
    global _cache

    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        return SecHealth(
            False,
            "SEC_USER_AGENT not configured (required for every SEC request)",
            None,
            time.time(),
        )

    timeout = (
        timeout
        if timeout is not None
        else _env_float("SEC_HEALTH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    )
    ttl = (
        ttl if ttl is not None else _env_float("SEC_HEALTH_TTL_SECONDS", DEFAULT_TTL_SECONDS)
    )
    probe_fn = probe or _probe

    with _cache_lock:
        cached = _cache
    if cached is not None and not force:
        if time.time() - cached.checked_at < ttl:
            return cached

    total = max(1, int(attempts))
    health = SecHealth(False, "SEC availability unknown", None, time.time())
    for attempt in range(total):
        health = probe_fn(SEC_HEALTH_URL, user_agent, timeout)
        if health.available:
            break
        if attempt + 1 < total:
            time.sleep(retry_delay)

    # The cache clock is owned here: probes need not set checked_at.
    health = replace(health, checked_at=time.time())
    with _cache_lock:
        _cache = health
    if not health.available:
        logger.warning("SEC preflight failed: %s", health.reason)
    else:
        logger.debug("SEC preflight ok (HTTP %s)", health.http_status)
    return health
