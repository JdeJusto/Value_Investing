"""One SEC EDGAR XBRL-facts client shared by the validation and audit scripts.

``scripts/audit_data_quality.py`` and ``scripts/validate_data_sample.py`` both
read annual figures straight from SEC's XBRL endpoints. They used to carry their
own transport, and only the audit knew how to recover an issuer whose per-tag
``companyconcept`` endpoint answers ``200`` with an empty envelope: the same
issuer then looked like a missing filing in the validation. This module is the
single implementation of both behaviours, including the fact parser, the tag
preference and the zero-value filter.

Everything here is read-only and never persists anything: HTTP responses are
cached in memory for the process lifetime and any failure degrades to ``None``.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

#: SEC asks for <= 10 requests/second; 0.12 s between calls keeps us under it.
SEC_MIN_INTERVAL_SECONDS = 0.12
SEC_TIMEOUT_SECONDS = 15.0
COMPANYCONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
)
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

#: Annual facts span a full year; a Q4 figure must not pass as the annual one.
ANNUAL_MIN_DAYS = 300
ANNUAL_MAX_DAYS = 400

#: A fact whose period end is within this many days of the audited year end is
#: taken to cover that year; a larger drift means the tag is stale.
PERIOD_MATCH_DAYS = 45

#: Attempts per HTTP request before the client degrades to ``None``.
HTTP_ATTEMPTS = 2


def split_tag(tag: str) -> tuple[str, str]:
    """``(taxonomy, concept)`` for ``"dei:EntityCommonStockSharesOutstanding"``.

    A bare concept name belongs to the default ``us-gaap`` taxonomy.
    """
    taxonomy, _, concept = tag.partition(":")
    if not concept:
        return "us-gaap", tag
    return taxonomy, concept


def parse_date(value: Any) -> date | None:
    """Parse an ISO date (tolerating a trailing time component), else ``None``."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def period_distance(period: date | None, reference: date | None) -> int:
    """Calendar-day distance between two periods (``0`` when either is missing)."""
    if period is None or reference is None:
        return 0
    return abs((period - reference).days)


def _duration_days(start: Any, end: Any) -> int | None:
    """Days between two ISO dates, or ``None`` when either is missing."""
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


@dataclass(frozen=True)
class Fact:
    """One annual value as filed: the value plus the period it belongs to."""

    value: float
    period_end: date | None = None
    tag: str | None = None
    form: str | None = None
    filed: str | None = None


def concept_has_facts(payload: Mapping[str, Any] | None) -> bool:
    """True when a ``companyconcept`` envelope actually carries facts.

    A ``200`` with an empty envelope (``{"units": {"USD": {}}}``) means "no
    data" and must not read as "the filing does not exist".
    """
    if not payload:
        return False
    for facts in (payload.get("units") or {}).values():
        if facts:
            return True
    return False


def annual_facts(
    concept: Mapping[str, Any] | None, fiscal_year_end: date | None
) -> list[Fact]:
    """Every annual (10-K / 10-K/A) fact in one ``companyconcept`` payload.

    Sorted so ``facts[0]`` is the value a reader takes from the filing series:
    the annual fact whose period end is closest to ``fiscal_year_end``, ties
    broken by the most recently filed fact. A later entry for the *same* period
    is therefore a superseded (pre-restatement) number.
    """
    if not concept:
        return []
    units = concept.get("units") or {}
    raw_facts = units.get("USD") or next(
        (unit for unit in units.values() if unit), None
    )
    if not raw_facts:
        return []

    facts: list[Fact] = []
    for raw in raw_facts:
        form = str(raw.get("form") or "").upper()
        if not form.startswith("10-K"):
            continue
        value = raw.get("val")
        if value is None:
            continue
        span = _duration_days(raw.get("start"), raw.get("end"))
        if span is not None and not (ANNUAL_MIN_DAYS <= span <= ANNUAL_MAX_DAYS):
            continue
        facts.append(
            Fact(
                value=float(value),
                period_end=parse_date(raw.get("end")),
                tag=None,
                form=form,
                filed=str(raw.get("filed") or "") or None,
            )
        )

    # Stable sorts, applied in reverse priority: filed desc, then distance asc.
    facts.sort(key=lambda fact: fact.filed or "", reverse=True)
    facts.sort(key=lambda fact: period_distance(fact.period_end, fiscal_year_end))
    return facts


def drop_zero_facts(facts: Sequence[Fact]) -> list[Fact]:
    """Without the zero-valued facts.

    A zero value in the SEC feed is either a placeholder or a missing-data
    artifact, never a year of aggregate revenue, assets or cash flow. Diluted
    EPS keeps its zeros (a zero year is a legitimate result).
    """
    return [fact for fact in facts if fact.value != 0]


def preferred_facts(
    by_tag: Mapping[str, list[Fact]], period: date | None = None
) -> tuple[str | None, list[Fact]]:
    """The tag whose annual fact best represents the audited fiscal period.

    Prefer the tag with the most recent filing that covers the fiscal period
    being compared. When several tags cover it, the most recently filed wins;
    ties (same ``filed`` date) fall back to the declared tag order, which lists
    the current taxonomy concept first (ASC 606 revenue, for instance). A tag
    whose best fact does not cover the period is only used when no tag does, so
    a retired tag with a recent re-filing, or a value from an old period, cannot
    mask the tag that is actually being filed today.
    """
    best_key: tuple[bool, str, int] | None = None
    best_tag: str | None = None
    best_facts: list[Fact] = []
    for index, (tag, facts) in enumerate(by_tag.items()):
        if not facts:
            continue
        chosen = facts[0]
        covers = (
            period is None
            or chosen.period_end is None
            or period_distance(chosen.period_end, period) <= PERIOD_MATCH_DAYS
        )
        key = (covers, chosen.filed or "", -index)
        if best_key is None or key > best_key:
            best_key, best_tag, best_facts = key, tag, facts
    return best_tag, best_facts


class SecFallbackFetcher:
    """Per-tag SEC fetch that recovers issuers with an empty concept endpoint.

    ``companyconcept`` occasionally answers ``200`` with an empty envelope for
    every tag of an issuer while its ``companyfacts`` document holds them all
    (Coca-Cola, observed 2026-10). Reading that emptiness as "no filing carries
    the figure" invents ``DATA_ERROR_FDB`` rows, so the first empty envelope
    switches that issuer to ``companyfacts`` for the rest of the run. The
    fallback costs one extra request per affected issuer and is recorded in the
    report so the substitution is never silent.

    The tag may name a taxonomy (``dei:EntityCommonStockSharesOutstanding``);
    the concept endpoint defaults to ``us-gaap`` and the fallback loads the
    matching taxonomy from ``companyfacts``.
    """

    def __init__(
        self,
        concept_fetch: Callable[[str, str], dict | None],
        concepts_loader: Callable[[str, str], dict[str, dict] | None],
    ) -> None:
        self._concept_fetch = concept_fetch
        self._concepts_loader = concepts_loader
        self._concepts: dict[tuple[str, str], dict[str, dict]] = {}
        self.fallback_issuers: set[str] = set()

    def __call__(self, cik: str, tag: str) -> dict | None:
        """The concept payload for ``tag``, from either SEC endpoint."""
        key = str(cik)
        taxonomy, concept = split_tag(tag)
        cache_key = (key, taxonomy)
        if cache_key in self._concepts:
            return self._concepts[cache_key].get(concept)
        payload = self._concept_fetch(key, tag)
        if payload is not None and not concept_has_facts(payload):
            self.fallback_issuers.add(key)
            self._concepts[cache_key] = self._concepts_loader(key, taxonomy) or {}
            return self._concepts[cache_key].get(concept)
        return payload


class SecFactsClient:
    """Minimal SEC XBRL client: paced, cached, and failure-tolerant.

    ``fetch`` is the per-tag call both scripts consume: it asks
    ``companyconcept`` first and falls back to ``companyfacts`` when an issuer's
    per-tag endpoint answers with an empty envelope. ``annual_facts`` /
    ``latest_annual`` layer the shared parsing, tag preference and zero filter on
    top so the audit and the validation derive the same number from the same
    filing.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float = SEC_TIMEOUT_SECONDS,
        min_interval: float = SEC_MIN_INTERVAL_SECONDS,
        opener: Callable[..., Any] | None = None,
        attempts: int = HTTP_ATTEMPTS,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._min_interval = max(0.0, min_interval)
        self._opener = opener or urllib.request.urlopen
        self._attempts = max(1, attempts)
        self._last_request = 0.0
        self._cache: dict[str, dict | None] = {}
        self.fetcher = SecFallbackFetcher(self.companyconcept, self.concepts)

    # -- transport ---------------------------------------------------------
    def _read(self, url: str) -> bytes | None:
        """One paced GET, or ``None`` on any transport failure."""
        self._pace()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return response.read()
        except Exception:  # noqa: BLE001 — any SEC failure just skips the tag
            return None

    def _get_json(self, url: str) -> dict | None:
        """GET one SEC JSON document (cached), or ``None`` on any failure."""
        if url in self._cache:
            return self._cache[url]
        payload: dict | None = None
        for _ in range(self._attempts):
            body = self._read(url)
            if body is None:
                continue
            try:
                payload = json.loads(body)
            except (TypeError, ValueError):
                payload = None
            break
        self._cache[url] = payload
        return payload

    def _pace(self) -> None:
        """Keep the request rate below SEC's 10 req/s guidance."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    # -- endpoints ---------------------------------------------------------
    def companyconcept(self, cik: str, tag: str) -> dict | None:
        """One concept for one CIK, or ``None`` on any failure.

        ``tag`` may name a taxonomy (``dei:EntityCommonStockSharesOutstanding``).
        """
        taxonomy, concept = split_tag(tag)
        url = COMPANYCONCEPT_URL.format(
            cik=str(cik).zfill(10), taxonomy=taxonomy, tag=concept
        )
        return self._get_json(url)

    def companyfacts(self, cik: str) -> dict | None:
        """The whole ``companyfacts`` document for one CIK, or ``None``."""
        return self._get_json(COMPANYFACTS_URL.format(cik=str(cik).zfill(10)))

    def concepts(self, cik: str, taxonomy: str = "us-gaap") -> dict[str, dict] | None:
        """All ``taxonomy`` concepts for one CIK, as ``{tag: {"units": ...}}``."""
        payload = self.companyfacts(cik)
        if payload is None:
            return None
        entries = (payload.get("facts") or {}).get(taxonomy) or {}
        return {
            tag: {"units": (entry or {}).get("units") or {}}
            for tag, entry in entries.items()
        }

    def fetch(self, cik: str, tag: str) -> dict | None:
        """The concept payload for ``tag``, with the ``companyfacts`` fallback."""
        return self.fetcher(cik, tag)

    # -- derived -----------------------------------------------------------
    def annual_facts(
        self,
        cik: str,
        tag: str,
        fiscal_year_end: date | None = None,
        *,
        keep_zero: bool = False,
    ) -> list[Fact]:
        """Annual facts for one tag, zeros dropped unless ``keep_zero``."""
        facts = annual_facts(self.fetch(cik, tag), fiscal_year_end)
        return facts if keep_zero else drop_zero_facts(facts)

    def facts(
        self,
        cik: str,
        tags: Sequence[str],
        fiscal_year_end: date | None = None,
        *,
        keep_zero: bool = False,
    ) -> dict[str, list[Fact]]:
        """Annual facts for every candidate tag that has any (empty dropped)."""
        by_tag: dict[str, list[Fact]] = {}
        for tag in tags:
            facts = self.annual_facts(cik, tag, fiscal_year_end, keep_zero=keep_zero)
            if facts:
                by_tag[tag] = facts
        return by_tag

    def latest_annual(
        self,
        cik: str,
        tags: Sequence[str],
        fiscal_year_end: date | None = None,
        *,
        keep_zero: bool = False,
    ) -> dict | None:
        """The fact the tag preference picks, as a plain mapping (or ``None``).

        Applies the same rules as the audit: the still-filed tag that covers
        ``fiscal_year_end`` wins, and zero-valued facts are placeholders unless
        the caller asks to keep them.
        """
        by_tag = self.facts(cik, tags, fiscal_year_end, keep_zero=keep_zero)
        tag, facts = preferred_facts(by_tag, fiscal_year_end)
        if not facts:
            return None
        fact = facts[0]
        return {
            "tag": tag,
            "value": fact.value,
            "period_end": fact.period_end,
            "filed": fact.filed,
        }

    @property
    def fallback_issuers(self) -> set[str]:
        """The CIKs whose per-tag endpoint was empty and fell back."""
        return self.fetcher.fallback_issuers
