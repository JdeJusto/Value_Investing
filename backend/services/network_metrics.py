"""Thread-safe network counters for a daily run.

Network-level metrics answer the questions the SEC/Yahoo symptoms raise
("was that a rate limit?", "were the syncs slow because SEC was slow?"),
which a wall-clock stage duration alone cannot. The daily workflow records
them here and they end up in the run state (``network`` section) and in the
daily report.

Granularity, stated plainly because it matters when reading the numbers:

- **Yahoo** metrics are measured at HTTP-call level: every ``.info`` /
  chart attempt performed by :class:`~backend.services.price_service.PriceService`
  is one request, a second attempt is a retry, and the elapsed time of the
  attempt is its latency.
- **SEC** metrics are measured per *company sync*, because VI never issues
  SEC HTTP calls itself: the targeted ``sec sync <CIK>`` runs as a
  subprocess (Financial-DataBase CLI). One attempt == one company sync (a
  handful of requests upstream), a transient failure counts as a retry (the
  next resumed run retries it) and a reason mentioning HTTP 403/429 is
  counted as such. Averages are therefore per-company-sync, not per request.

Everything degrades quietly: the counters are optional everywhere they are
injected, and any recording failure is swallowed. Nothing here performs I/O
and no price is ever persisted.
"""

from __future__ import annotations

import threading

SERVICE_SEC = "sec"
SERVICE_YAHOO = "yahoo"

# Fields published in the run state / report (the documented contract).
NETWORK_FIELDS = (
    "sec_requests",
    "sec_retries",
    "sec_403_count",
    "sec_429_count",
    "yahoo_requests",
    "yahoo_retries",
    "avg_sec_latency_ms",
    "avg_yahoo_latency_ms",
)


class NetworkMetrics:
    """Per-run network counters, safe to update from the worker threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {service: {"requests": n, "retries": n, "http_403": n, "http_429": n,
        #            "latency_ms": total, "samples": n}}
        self._counters: dict[str, dict[str, float]] = {}
        # Price-failure categories (yahoo_glitch/mapping/delisted/unknown/no_yahoo).
        self._price_failures: dict[str, int] = {}

    # ------------------------------------------------------------------
    def _bucket(self, service: str) -> dict[str, float]:
        return self._counters.setdefault(
            service,
            {
                "requests": 0,
                "retries": 0,
                "http_403": 0,
                "http_429": 0,
                "latency_ms": 0.0,
                "samples": 0,
            },
        )

    def record(
        self,
        service: str,
        *,
        latency_ms: float | None = None,
        retries: int = 0,
        http_status: int | None = None,
        reason: str | None = None,
    ) -> None:
        """Record one network attempt for ``service`` (``sec`` / ``yahoo``).

        ``retries`` counts *extra* attempts; ``http_status`` / ``reason`` are
        scanned for 403 (rate limit / non-compliant User-Agent) and 429
        (too many requests) so upstream throttling is visible in the report
        even when the failure only surfaces as a message.
        """
        try:
            with self._lock:
                bucket = self._bucket(service)
                bucket["requests"] += 1
                if retries:
                    bucket["retries"] += int(retries)
                blob = f"{http_status or ''} {reason or ''}"
                if "403" in blob:
                    bucket["http_403"] += 1
                if "429" in blob:
                    bucket["http_429"] += 1
                if latency_ms is not None:
                    bucket["latency_ms"] += float(latency_ms)
                    bucket["samples"] += 1
        except Exception:  # noqa: BLE001, S110 — telemetry must never break a run
            pass

    def record_failure(self, service: str, reason: str, *, latency_ms: float | None = None) -> None:
        """Record a failed attempt (counted as a request + 1 retry)."""
        self.record(service, latency_ms=latency_ms, retries=1, reason=reason)

    def note_status(self, service: str, status: int | None) -> None:
        """Count a bare HTTP status (used when a client exposes it)."""
        if status in (403, 429):
            self.record(service, http_status=int(status))

    def note_price_failure(self, category: str, count: int = 1) -> None:
        """Tally one price-failure category (glitch/mapping/delisted/...).

        Kept apart from the HTTP counters on purpose: a failure category is a
        conclusion about a company (or about the provider being down), not a
        transport fact, and the run state reports them in their own section.
        """
        try:
            with self._lock:
                failures = self._price_failures.setdefault(str(category), 0)
                self._price_failures[str(category)] = failures + int(count)
        except Exception:  # noqa: BLE001, S110 — telemetry must never break a run
            pass

    def price_failures(self) -> dict[str, int]:
        """Per-category price failure tally (empty when nothing failed)."""
        with self._lock:
            return dict(self._price_failures)

    # ------------------------------------------------------------------
    def _avg_latency_ms(self, service: str) -> float:
        bucket = self._counters.get(service) or {}
        samples = bucket.get("samples", 0)
        if not samples:
            return 0.0
        return round(bucket.get("latency_ms", 0.0) / float(samples), 1)

    def snapshot(self) -> dict[str, int | float]:
        """The documented ``network`` payload (all fields, always present)."""
        with self._lock:
            sec = dict(self._counters.get(SERVICE_SEC) or {})
            yahoo = dict(self._counters.get(SERVICE_YAHOO) or {})
        return {
            "sec_requests": int(sec.get("requests", 0)),
            "sec_retries": int(sec.get("retries", 0)),
            "sec_403_count": int(sec.get("http_403", 0)),
            "sec_429_count": int(sec.get("http_429", 0)),
            "yahoo_requests": int(yahoo.get("requests", 0)),
            "yahoo_retries": int(yahoo.get("retries", 0)),
            "avg_sec_latency_ms": self._avg_latency_ms(SERVICE_SEC),
            "avg_yahoo_latency_ms": self._avg_latency_ms(SERVICE_YAHOO),
        }

    def is_empty(self) -> bool:
        with self._lock:
            return not any(
                bucket.get("requests", 0) for bucket in self._counters.values()
            )

    def summary(self) -> str:
        """One-line human summary for the workflow log."""
        data = self.snapshot()
        if not any(data.values()):
            return "network: no calls recorded"
        return (
            f"SEC syncs {data['sec_requests']} (retries {data['sec_retries']}, "
            f"403 {data['sec_403_count']}, 429 {data['sec_429_count']}, "
            f"avg {data['avg_sec_latency_ms']:.0f} ms) | "
            f"Yahoo requests {data['yahoo_requests']} "
            f"(retries {data['yahoo_retries']}, "
            f"avg {data['avg_yahoo_latency_ms']:.0f} ms)"
        )
