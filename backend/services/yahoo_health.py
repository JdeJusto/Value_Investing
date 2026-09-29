"""Yahoo Finance availability preflight.

Yahoo is the only source of market data for Value Investing (prices are
fetched on demand and never persisted), and it fails in a way that is
expensive to discover late: a universe-sized run can be cut off mid-flight
by throttling, and every price-derived metric (P/E, P/B, FCF yield, EV/EBIT,
margin of safety) degrades to N/A. A preflight turns a slow, confusing
half-run into a single clear skip: the fundamentals analysis still runs and
the report says why the market fields are empty.

**The probe walks the same path the data does.** That is the whole point of
this module, and getting it wrong was a real incident: an earlier version
probed only ``/v8/finance/chart`` on ``query1`` and answered HTTP 200 while
``yfinance`` was being served HTTP 429 on its crumb fetch and then
``401 Invalid Crumb``. A green preflight that does not exercise the real path
is worse than no preflight: it authorises a 2 528-ticker run that cannot
succeed. yfinance 1.7.0 (``yfinance/data.py``) does, in order:

1. **cookie** — ``GET https://fc.yahoo.com`` (redirects followed). yfinance
   treats this as non-critical and degrades without it, so a failure here is
   reported but does not fail the probe;
2. **crumb** — ``GET https://query1.finance.yahoo.com/v1/test/getcrumb`` with
   that cookie. This is the fragile step: yfinance raises
   ``YFRateLimitError`` on HTTP 429 or a "Too Many Requests" body, and an
   unusable crumb makes every later request answer 401;
3. **quote** — ``GET https://query2.finance.yahoo.com/v8/finance/chart/AAPL``
   with the crumb. Note ``query2``: yfinance's ``_BASE_URL_`` is query2 while
   the crumb comes from query1, so probing only one host is not enough.

Each stage is reported (:attr:`YahooHealth.stage`), so a failure says *which*
step broke instead of a bare "unavailable". The result is cached for 120 s per
process, mirroring the SEC preflight in :mod:`backend.services.sec_health`.

The probe is injectable, so tests never touch the network, and no price is
read, stored or reported by this module.
"""

from __future__ import annotations

import http.cookiejar
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Callable, Optional

logger = logging.getLogger("backend.yahoo_health")

# The three endpoints above, in the order yfinance uses them. The chart URL is
# kept as a module constant for the stage-3 quote check (1 day / 1d keeps the
# body tiny: a few KB).
YAHOO_CHART_URL = (
    "https://query2.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d"
)
YAHOO_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
YAHOO_COOKIE_URL = "https://fc.yahoo.com"

# Backwards-compatible alias: the name used before the probe grew a path.
YAHOO_HEALTH_URL = YAHOO_CHART_URL

# Stages, in path order. "unknown" means the probe never classified itself
# (a probe callable supplied by a test, for instance).
STAGE_COOKIE = "cookie"
STAGE_CRUMB = "crumb"
STAGE_QUOTE = "quote"
# The stage that matters: the probe asked yfinance itself.
STAGE_YFINANCE = "yfinance"
STAGE_UNKNOWN = "unknown"

# Probe User-Agent: minimal on purpose.
#
# Why so plain? Measured on 2026-09-27 from this host, same URL, same IP, same
# instant, only the header differing: a full Chrome UA
# ("Mozilla/5.0 (X11; Linux x86_64) … Chrome/120.0 Safari/537.36") got HTTP 429
# while "Mozilla/5.0" got HTTP 200. A browser-like UA without cookies or a
# crumb is what bot detection fingerprints as an unsatisfied browser client,
# so the preflight was being refused on its own header and taking the whole
# price stage down with it. Do not "improve" this string: a minimal agent is
# the one that is served. See docs/price_recovery_2026-09-28.md.
#
# PriceService itself sets no User-Agent: its data path is yfinance, which
# manages its own (and demonstrably works: 506 requests, 2 transient
# failures). This constant therefore covers the only agent we control.
#
# Override with YAHOO_HEALTH_USER_AGENT if a deployment needs another.
DEFAULT_USER_AGENT = "Mozilla/5.0"

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_ATTEMPTS = 2  # one retry absorbs transient failures
DEFAULT_RETRY_DELAY_SECONDS = 0.5
DEFAULT_TTL_SECONDS = 120.0


@dataclass(frozen=True)
class YahooHealth:
    """Outcome of one Yahoo availability probe.

    ``stage`` says *which* step of the path broke (see the module docstring):
    ``cookie`` is advisory (yfinance degrades without it), while ``crumb`` and
    ``quote`` make the data path unusable. ``rate_limited`` is the flag the
    price stage acts on: a 429 is not something retries can fix.
    """

    available: bool
    reason: str
    http_status: Optional[int] = None
    checked_at: float = 0.0
    stage: str = STAGE_UNKNOWN
    crumb: bool = False

    @property
    def rate_limited(self) -> bool:
        return self.http_status == 429 or "429" in self.reason or "rate limit" in self.reason.lower()

    @property
    def non_transient(self) -> bool:
        """True when retrying cannot help: 429 (rate limit) or 401 (crumb)."""
        return self.http_status in (401, 429) or self.rate_limited


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


def _user_agent() -> str:
    return (
        os.environ.get("YAHOO_HEALTH_USER_AGENT", DEFAULT_USER_AGENT).strip()
        or DEFAULT_USER_AGENT
    )


def _http_error_health(exc: urllib.error.HTTPError, stage: str) -> YahooHealth:
    """Map an HTTP error to a health verdict, keeping the stage that failed."""
    now = time.time()
    if exc.code == 429:
        return YahooHealth(
            False,
            f"Yahoo returned HTTP 429 at the {stage} step (rate limited)",
            exc.code,
            now,
            stage=stage,
        )
    if exc.code == 401:
        return YahooHealth(
            False,
            f"Yahoo returned HTTP 401 at the {stage} step (unauthorized / bad crumb)",
            exc.code,
            now,
            stage=stage,
        )
    if exc.code == 404:
        return YahooHealth(
            False, f"Yahoo returned HTTP 404 at the {stage} step", exc.code, now,
            stage=stage,
        )
    return YahooHealth(
        False, f"Yahoo returned HTTP {exc.code} at the {stage} step", exc.code, now,
        stage=stage,
    )


def _fetch(
    url: str,
    timeout: float,
    opener: Callable[[urllib.request.Request, float], object],
    stage: str,
):
    """One GET through ``opener``; returns (status, body-text) or raises."""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/json",
        },
    )
    # NOTE: OpenerDirector.open(url, data=None, timeout=...) — the timeout must
    # be a keyword, otherwise it is sent as the request body.
    with opener(request, timeout=timeout) as response:
        status = getattr(response, "status", None) or response.getcode()
        # The crumb is tiny; the chart body is a few KB and we only need enough
        # of it to prove the endpoint answered with data.
        body = response.read(4096)
        text = body.decode("utf-8", "replace") if body else ""
        return int(status), text


def _probe(timeout: float) -> YahooHealth:
    """Is the real data path usable right now?

    Asks **yfinance itself** first, because it is the only client that walks
    Yahoo's path successfully: it uses ``curl_cffi`` with browser
    impersonation, and a plain ``urllib`` client is refused at the crumb step
    with HTTP 406 even while ``yfinance`` is being served normally (measured
    2026-09-27). A preflight that answers a different question than the data
    asks is the bug this whole change exists to remove.

    ``fast_info`` is the cheapest yfinance call that still exercises the
    session (it is the one that raises on a rate limit instead of returning an
    empty dict), so it is the probe; the urllib walk below is the fallback for
    environments where yfinance cannot be imported.
    """
    health = _probe_via_yfinance()
    if health is not None:
        return health
    return _probe_via_http(timeout)


def _probe_via_yfinance() -> Optional[YahooHealth]:
    """One ``fast_info`` call. None when yfinance is not importable here."""
    try:
        import yfinance as yf
    except Exception as exc:
        logger.debug("yahoo preflight: yfinance not importable (%s)", exc)
        return None

    ticker = yf.Ticker("AAPL")
    try:
        info = ticker.fast_info
    except Exception as exc:
        return _verdict_from_exception(exc, stage=STAGE_YFINANCE)
    try:
        price = float(info["lastPrice"]) if info is not None else 0.0
    except Exception:
        price = 0.0
    if price > 0:
        return YahooHealth(
            True,
            "ok",
            200,
            time.time(),
            stage=STAGE_YFINANCE,
            crumb=True,
        )
    return YahooHealth(
        False,
        "yfinance returned no price for the probe symbol",
        None,
        time.time(),
        stage=STAGE_YFINANCE,
    )


def _verdict_from_exception(exc: Exception, stage: str) -> YahooHealth:
    """Classify a yfinance exception into a health verdict.

    ``YFRateLimitError`` means 429 and ``Invalid Crumb``/401 means the session
    is not usable; both are non-transient (retrying cannot help). Everything
    else (5xx, timeouts, DNS) is treated as transient so it still retries.
    """
    now = time.time()
    text = str(exc)
    lowered = text.lower()
    type_name = type(exc).__name__

    if "ratelimit" in type_name.lower() or "too many requests" in lowered or "429" in text:
        return YahooHealth(
            False, f"Yahoo rate limited ({type_name}) at the {stage} step", 429, now,
            stage=stage,
        )
    if "invalid crumb" in lowered or "401" in text or "unauthorized" in lowered:
        return YahooHealth(
            False,
            f"Yahoo rejected the session ({type_name}: invalid crumb) at the {stage} step",
            401,
            now,
            stage=stage,
        )
    return YahooHealth(
        False, f"Yahoo probe failed at the {stage} step: {type_name}: {text}", None, now,
        stage=stage,
    )


def _probe_via_http(timeout: float) -> YahooHealth:
    """Walk Yahoo's path with plain HTTP: cookie -> crumb -> quote.

    Mirrors ``yfinance.data.YfData._get`` (1.7.0) closely enough to localise a
    broken step, and is the fallback when yfinance is not importable. Note it
    is *not* equivalent for throttling purposes: Yahoo serves the chart
    endpoint to a minimal agent while refusing the crumb endpoint, which is
    exactly how the preflight used to be green during a real rate limit.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    now = time.time()

    # 1. Cookie — advisory. yfinance degrades without it (it is non-critical
    # behind some proxies), so a failure is reported in the reason but does
    # not by itself mean the provider is unusable.
    cookie_ok = True
    try:
        request = urllib.request.Request(
            YAHOO_COOKIE_URL,
            method="GET",
            headers={"User-Agent": _user_agent()},
        )
        with opener.open(request, timeout=timeout) as response:
            response.read(64)
    except urllib.error.HTTPError as exc:
        cookie_ok = False
        logger.debug("yahoo preflight: cookie step returned HTTP %s", exc.code)
    except Exception as exc:
        cookie_ok = False
        logger.debug("yahoo preflight: cookie step failed: %s", exc)

    # 2. Crumb — the fragile one. yfinance raises YFRateLimitError on 429 and
    # gets "401 Invalid Crumb" on every later request without a usable crumb.
    crumb_text = ""
    try:
        _status, crumb_text = _fetch(YAHOO_CRUMB_URL, timeout, opener.open, STAGE_CRUMB)
    except urllib.error.HTTPError as exc:
        return _http_error_health(exc, STAGE_CRUMB)
    except Exception as exc:
        return YahooHealth(
            False, f"Yahoo unreachable at the crumb step: {exc}", None, now,
            stage=STAGE_CRUMB,
        )

    if "Too Many Requests" in crumb_text:
        return YahooHealth(
            False,
            "Yahoo returned 'Too Many Requests' at the crumb step (rate limited)",
            429,
            time.time(),
            stage=STAGE_CRUMB,
        )
    crumb = crumb_text.strip()
    if not crumb or "<html>" in crumb.lower():
        return YahooHealth(
            False,
            "Yahoo returned no usable crumb (empty or HTML body)",
            None,
            time.time(),
            stage=STAGE_CRUMB,
        )

    # 3. Quote with the crumb, on the host yfinance actually uses (query2).
    request = urllib.request.Request(
        YAHOO_CHART_URL,
        method="GET",
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/json",
            # yfinance sends the crumb as a query parameter; a stale one is
            # exactly what produces "401 Invalid Crumb".
            **({"crumb": crumb} if crumb else {}),
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            response.read(64)
    except urllib.error.HTTPError as exc:
        return _http_error_health(exc, STAGE_QUOTE)
    except Exception as exc:
        return YahooHealth(
            False, f"Yahoo unreachable at the quote step: {exc}", None, time.time(),
            stage=STAGE_QUOTE,
        )

    reason = "ok"
    if not cookie_ok:
        reason = "ok (cookie step degraded; Yahoo serves data without it)"
    return YahooHealth(
        True, reason, int(status), time.time(), stage=STAGE_QUOTE, crumb=True
    )


def check_yahoo_availability(
    *,
    timeout: Optional[float] = None,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ttl: Optional[float] = None,
    force: bool = False,
    probe: Optional[Callable[..., YahooHealth]] = None,
) -> YahooHealth:
    """Return (and cache) whether Yahoo Finance is usable right now.

    The probe walks cookie -> crumb -> quote, i.e. the same path
    :class:`~backend.services.price_service.PriceService` will walk, so a green
    verdict means the data path works. ``YahooHealth.stage`` names the step
    that failed, and :attr:`YahooHealth.non_transient` marks the failures
    (401/429) that retrying cannot fix.

    - ``attempts`` tries (default 2: one retry spaced by ``retry_delay``), but
      a **non-transient** failure is *not* retried: 429 means "come back
      later", and hammering it twice is what turns one refusal into a
      throttle.
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
    health = YahooHealth(
        False, "Yahoo availability unknown", None, time.time(), stage=STAGE_UNKNOWN
    )
    for attempt in range(total):
        try:
            # The probe takes just the timeout; a custom one may still accept
            # the (url, timeout) pair from the previous signature.
            try:
                health = probe_fn(timeout)
            except TypeError:
                health = probe_fn(YAHOO_CHART_URL, timeout)
        except Exception as exc:
            health = YahooHealth(
                False, f"Yahoo preflight error: {exc}", None, time.time(),
                stage=STAGE_UNKNOWN,
            )
        if health.available:
            break
        if health.non_transient:
            logger.debug(
                "yahoo preflight: not retrying a non-transient %s failure",
                health.http_status,
            )
            break
        if attempt + 1 < total:
            time.sleep(retry_delay)

    # The cache clock is owned here: probes need not set checked_at.
    health = replace(health, checked_at=time.time())
    with _cache_lock:
        _cache = health
    if not health.available:
        logger.warning(
            "Yahoo preflight failed at the %s step: %s", health.stage, health.reason
        )
    else:
        logger.debug(
            "Yahoo preflight ok (HTTP %s, stage %s)", health.http_status, health.stage
        )
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
