#!/usr/bin/env python3
"""Cross-source data-quality audit with classified discrepancies.

Where ``scripts/validate_data_sample.py`` answers *"does the number differ?"*,
this audit answers *"why does it differ, and does it matter?"*. For a
reproducible sample of the universe it reads each company's latest completed
fiscal year from Financial-DataBase (**read-only**, never written), fetches the
same figures from SEC EDGAR's ``companyconcept`` API and — when asked — from
Yahoo Finance, and classifies every discrepancy with a deterministic heuristic:

``MATCH``                within tolerance (an opposite sign on a cash-flow line
                         with the same magnitude is a sign convention, not a bug)
``DIFFERENT_PERIOD``     the two sources anchor on different fiscal periods
``DIFFERENT_TAG``        the DB value is real but lives under another XBRL tag
``SPLIT_ADJUSTMENT``     the ratio matches a known split factor
``RESTATEMENT``          the value matches a superseded filing of the same period
``DATA_ERROR_FDB``       the DB value traces to no SEC filing at all (a bug)
``DATA_ERROR_EXTERNAL``  the authoritative source confirms the DB, the other is wrong
``UNCLASSIFIED``         explained by none of the above; needs manual review

The classifier is heuristic, never an LLM, and never writes to a database: the
only output is ``logs/audit_data_quality_<YYYY-MM-DD>.{log,json,csv}``. Prices
are read (only for split factors) and never persisted.

Usage::

    python -m scripts.audit_data_quality --sample 50
    python -m scripts.audit_data_quality --tickers AAPL,KO,JPM
    python -m scripts.audit_data_quality --sample 50 --sources sec,yahoo

Exit codes:
    0  every discrepancy is expected (no ``DATA_ERROR_*``)
    1  at least one ``DATA_ERROR_FDB`` was flagged
    2  the audit could not run (no database, no network, no SEC contact)
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_data_sample import (
    DEFAULT_UNIVERSE,
    SEC_TIMEOUT_SECONDS,
    SecCompanyFactsClient,
    SecConceptClient,
    choose_sample,
    concept_has_facts,
    load_sp500_universe,
    pct_difference,
)

DEFAULT_OUT_DIR = PROJECT_ROOT / "logs"
DEFAULT_SAMPLE_SIZE = 50
DEFAULT_SEED = 42
DEFAULT_SOURCES = "sec,yahoo"

#: Two period ends closer than this are considered the same fiscal period.
PERIOD_MATCH_DAYS = 45

#: A larger drift than this is not a period artifact but a tag that simply has no
#: fact for the audited year (revenue tags retired after ASC 606, say). Treating
#: a seven-year gap as "the periods differ" would hide a genuinely wrong value.
PERIOD_SHIFT_DAYS = 400

#: Financial-DataBase is always side A; these are the optional other sides.
SUPPORTED_SOURCES = ("sec", "yahoo")
#: Requested-but-unavailable sources, with the reason recorded in the report.
SKIPPED_SOURCES: dict[str, str] = {
    "stockanalysis": "no public API without HTML scraping; skipped by default",
    "macrotrends": "no public API without HTML scraping; skipped by default",
}

# --- classifications -------------------------------------------------------
MATCH = "MATCH"
DIFFERENT_PERIOD = "DIFFERENT_PERIOD"
DIFFERENT_TAG = "DIFFERENT_TAG"
SPLIT_ADJUSTMENT = "SPLIT_ADJUSTMENT"
RESTATEMENT = "RESTATEMENT"
DATA_ERROR_FDB = "DATA_ERROR_FDB"
DATA_ERROR_EXTERNAL = "DATA_ERROR_EXTERNAL"
UNCLASSIFIED = "UNCLASSIFIED"
SKIPPED = "SKIPPED"

#: The suggested action per classification (the audit's contract with a reader).
ACTIONS: dict[str, str] = {
    MATCH: "none",
    DIFFERENT_PERIOD: "none, expected",
    DIFFERENT_TAG: "consider mapping both",
    SPLIT_ADJUSTMENT: "verify the split factor",
    RESTATEMENT: "none, expected",
    DATA_ERROR_FDB: "investigate and fix",
    DATA_ERROR_EXTERNAL: "none, log",
    UNCLASSIFIED: "manual review",
    SKIPPED: "none, not comparable",
}

#: Classifications that mean "nothing to fix".
EXPECTED = frozenset(
    {MATCH, DIFFERENT_PERIOD, DIFFERENT_TAG, SPLIT_ADJUSTMENT, RESTATEMENT}
)

#: Annual facts span a full year; a Q4 figure must not pass as the annual one.
ANNUAL_MIN_DAYS = 300
ANNUAL_MAX_DAYS = 400


# ---------------------------------------------------------------------------
# metric catalogue
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MetricSpec:
    """One audited metric: how to read it and how much difference is noise.

    ``tags`` are the SEC concepts tried in order and listed **most current
    first**. The audit prefers the tag with the most recent filing that covers
    the audited fiscal period (:func:`_preferred`); this order only breaks a
    tie between tags filed the same day, so the current taxonomy concept wins
    (ASC 606 revenue over the retired ``Revenues``/``SalesRevenueNet``).
    ``attribute`` names the Financial-DataBase/``NormalizedFinancials`` field;
    ``derive`` names a formula in :data:`DERIVATIONS` for metrics with no direct
    field.

    ``strict`` means "every filer discloses this line", so a value that traces
    to no SEC filing is a defect; a non-strict metric simply may not be tagged.
    ``magnitude_only`` tolerates a pure sign flip (cash-flow convention).
    """

    metric: str
    tolerance_pct: float
    tags: tuple[str, ...]
    attribute: str | None = None
    derive: str | None = None
    magnitude_only: bool = False
    strict: bool = True


AUDIT_METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "revenue",
        2.0,
        (
            # ASC 606 concepts are current; ``Revenues``/``SalesRevenueNet`` were
            # retired around 2018 but their old facts linger in the SEC feed.
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ),
        attribute="revenue",
    ),
    MetricSpec(
        "net_income",
        5.0,
        ("NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"),
        attribute="net_income",
    ),
    MetricSpec("total_assets", 2.0, ("Assets",), attribute="total_assets"),
    MetricSpec(
        "total_liabilities", 2.0, ("Liabilities",), attribute="total_liabilities"
    ),
    MetricSpec(
        "stockholders_equity",
        2.0,
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        attribute="stockholders_equity",
        strict=False,
    ),
    MetricSpec(
        "operating_cash_flow",
        5.0,
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        attribute="operating_cash_flow",
    ),
    MetricSpec(
        "capital_expenditure",
        5.0,
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsForCapitalImprovements",
        ),
        attribute="capital_expenditure",
        magnitude_only=True,
        strict=False,
    ),
    MetricSpec(
        "shares_outstanding",
        2.0,
        ("CommonStockSharesOutstanding", "CommonStockSharesIssued"),
        attribute="shares_outstanding",
        strict=False,
    ),
    MetricSpec(
        "eps_diluted",
        5.0,
        ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"),
        derive="eps_diluted",
        strict=False,
    ),
    MetricSpec(
        "dividends_per_share",
        5.0,
        (
            "CommonStockDividendsPerShareDeclared",
            "CommonStockDividendsPerShareCashPaid",
        ),
        derive="dividends_per_share",
        strict=False,
    ),
)


def _divide(numerator: Any, denominator: Any) -> float | None:
    """``numerator / denominator``, or None when that is undefined."""
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


#: ``(formula, callable)`` for metrics the normalized payload has no field for.
DERIVATIONS: dict[str, tuple[str, Callable[[Any], float | None]]] = {
    "eps_diluted": (
        "net_income / shares_outstanding",
        lambda payload: _divide(
            getattr(payload, "net_income", None),
            getattr(payload, "shares_outstanding", None),
        ),
    ),
    "dividends_per_share": (
        "dividends_paid / shares_outstanding",
        lambda payload: _divide(
            getattr(payload, "dividends_paid", None),
            getattr(payload, "shares_outstanding", None),
        ),
    ),
}


def metric_value(financials: Any, spec: MetricSpec) -> float | None:
    """Read one metric off a normalized payload (derived when needed)."""
    if spec.derive is not None:
        return DERIVATIONS[spec.derive][1](financials)
    if spec.attribute is None:
        return None
    value = getattr(financials, spec.attribute, None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Fact:
    """One annual value as filed: the value plus the period it belongs to."""

    value: float
    period_end: date | None = None
    tag: str | None = None
    form: str | None = None
    filed: str | None = None


def _parse_date(value: Any) -> date | None:
    """Parse an ISO date (tolerating a trailing time component), else None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


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
                period_end=_parse_date(raw.get("end")),
                tag=None,
                form=form,
                filed=str(raw.get("filed") or "") or None,
            )
        )

    # Stable sorts, applied in reverse priority: filed desc, then distance asc.
    facts.sort(key=lambda fact: fact.filed or "", reverse=True)
    facts.sort(key=lambda fact: _distance(fact.period_end, fiscal_year_end))
    return facts


def _distance(period: date | None, reference: date | None) -> int:
    """Calendar-day distance between two periods (0 when either is missing)."""
    if period is None or reference is None:
        return 0
    return abs((period - reference).days)


def _duration_days(start: Any, end: Any) -> int | None:
    """Days between two ISO dates, or None when either is missing."""
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


def sec_metric_facts(
    cik: str,
    spec: MetricSpec,
    sec_fetcher: Callable[[str, str], dict | None],
    fiscal_year_end: date | None,
) -> dict[str, list[Fact]]:
    """Annual facts for one metric, keyed by tag (empty tags dropped)."""
    by_tag: dict[str, list[Fact]] = {}
    for tag in spec.tags:
        facts = annual_facts(sec_fetcher(str(cik), tag), fiscal_year_end)
        if facts:
            by_tag[tag] = facts
    return by_tag


def _preferred(
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
            or _distance(chosen.period_end, period) <= PERIOD_MATCH_DAYS
        )
        key = (covers, chosen.filed or "", -index)
        if best_key is None or key > best_key:
            best_key, best_tag, best_facts = key, tag, facts
    return best_tag, best_facts


# ---------------------------------------------------------------------------
# classification (pure)
# ---------------------------------------------------------------------------
def _within_tolerance(
    value: float | None, other: float | None, tolerance_pct: float
) -> bool:
    """True when both exist and their relative difference is within tolerance."""
    difference = pct_difference(value, other)
    return difference is not None and difference <= tolerance_pct


def _ratio_matches(ratio: float, factor: float, tolerance_pct: float) -> bool:
    """True when ``ratio`` equals ``factor`` within the metric's tolerance."""
    if factor == 0:
        return False
    return abs(ratio - factor) / abs(factor) * 100.0 <= tolerance_pct


def classify_comparison(
    *,
    value_a: float | None,
    value_b: float | None,
    tolerance_pct: float,
    period_a: date | None = None,
    period_b: date | None = None,
    authoritative: bool = True,
    upstream_available: bool = True,
    strict: bool = True,
    magnitude_only: bool = False,
    alternative_tags: Mapping[str, Sequence[Fact]] | None = None,
    restated: Sequence[Fact] = (),
    split_factor: float | None = None,
    authoritative_agrees: bool | None = None,
    period_days: int = PERIOD_MATCH_DAYS,
    period_shift_days: int = PERIOD_SHIFT_DAYS,
) -> tuple[str, str]:
    """Classify one side-A vs side-B comparison. Returns ``(class, reason)``.

    Heuristics only, evaluated by decreasing certainty: tolerance, sign, period
    drift, split, restatement, alternative tag, then "who is authoritative". A
    drift counts as a period artifact only within ``period_shift_days``: a
    larger gap means the preferred tag has no fact for the audited year, not
    that the two periods disagree. A missing value is ``SKIPPED`` — except when
    the caller knows the authoritative source has no fact at all
    (``upstream_available=False``), which is what a strict metric calls a defect.
    """
    if value_a is None:
        return SKIPPED, "value missing on the Financial-DataBase side"
    if value_b is None:
        if not upstream_available and authoritative:
            if strict:
                return DATA_ERROR_FDB, "no SEC filing carries this figure"
            # Filers may legitimately not tag this line; that is not a defect.
            return SKIPPED, "the SEC filing does not tag this line"
        return SKIPPED, "value missing on the other side"

    difference = pct_difference(value_a, value_b)
    if difference is not None and difference <= tolerance_pct:
        return MATCH, f"within the {tolerance_pct:g}% tolerance"
    if (
        magnitude_only
        and difference is not None
        and (value_a < 0) != (value_b < 0)
        and _within_tolerance(abs(value_a), abs(value_b), tolerance_pct)
    ):
        return MATCH, "same magnitude, opposite sign (cash-flow sign convention)"

    if period_a and period_b:
        drift = _distance(period_a, period_b)
        if period_days < drift <= period_shift_days:
            return (
                DIFFERENT_PERIOD,
                f"period ends differ by {drift} days ({period_a} vs {period_b})",
            )

    if split_factor and split_factor > 0 and value_b:
        ratio = value_a / value_b
        if _ratio_matches(ratio, split_factor, tolerance_pct) or _ratio_matches(
            ratio, 1.0 / split_factor, tolerance_pct
        ):
            return (
                SPLIT_ADJUSTMENT,
                f"ratio {ratio:.4g} matches the {split_factor:g}x split factor",
            )

    for fact in restated:
        if (
            period_a is not None
            and fact.period_end is not None
            and _distance(fact.period_end, period_a) <= period_days
            and _within_tolerance(value_a, fact.value, tolerance_pct)
        ):
            return (
                RESTATEMENT,
                "matches a superseded filing of the same period (amended 10-K)",
            )

    for tag, facts in (alternative_tags or {}).items():
        if not facts:
            continue
        candidate = facts[0]
        # Only a tag that carries the *audited* period can explain the value.
        period_known = candidate.period_end is not None and period_a is not None
        if period_known and _distance(candidate.period_end, period_a) > period_days:
            continue
        if _within_tolerance(value_a, candidate.value, tolerance_pct):
            return (
                DIFFERENT_TAG,
                f"the DB value matches the SEC tag {tag}, not the preferred one",
            )

    if not authoritative:
        if authoritative_agrees:
            return DATA_ERROR_EXTERNAL, "the authoritative source confirms the DB value"
        return UNCLASSIFIED, "no authoritative reference to attribute the difference to"

    return UNCLASSIFIED, "the SEC value differs and no heuristic explains why"


# ---------------------------------------------------------------------------
# report rows
# ---------------------------------------------------------------------------
def comparison_row(
    *,
    ticker: str,
    metric: str,
    source: str,
    value_a: float | None,
    value_b: float | None,
    classification: str,
    reason: str,
    period_a: date | None = None,
    period_b: date | None = None,
) -> dict[str, Any]:
    """One comparison record (also the CSV shape)."""
    return {
        "ticker": ticker,
        "metric": metric,
        "source_a": "financial_database",
        "source_b": source,
        "value_a": value_a,
        "value_b": value_b,
        "delta_pct": pct_difference(value_a, value_b),
        "classification": classification,
        "action": ACTIONS.get(classification, "manual review"),
        "reason": reason,
        "period_a": period_a.isoformat() if period_a else None,
        "period_b": period_b.isoformat() if period_b else None,
    }


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
class SecFallbackFetcher:
    """Per-tag SEC fetch that recovers issuers with an empty concept endpoint.

    ``companyconcept`` occasionally answers ``200`` with an empty envelope for
    every tag of an issuer while its ``companyfacts`` document holds them all
    (Coca-Cola, observed 2026-10). Reading that emptiness as "no filing carries
    the figure" invents ``DATA_ERROR_FDB`` rows, so the first empty envelope
    switches that issuer to ``companyfacts`` for the rest of the run. The
    fallback costs one extra request per affected issuer and is recorded in the
    report so the substitution is never silent.
    """

    def __init__(
        self,
        concept_fetch: Callable[[str, str], dict | None],
        concepts_loader: Callable[[str], dict[str, dict] | None],
    ) -> None:
        self._concept_fetch = concept_fetch
        self._concepts_loader = concepts_loader
        self._concepts: dict[str, dict[str, dict]] = {}
        self.fallback_issuers: set[str] = set()

    def __call__(self, cik: str, tag: str) -> dict | None:
        """The concept payload for ``tag``, from either SEC endpoint."""
        key = str(cik)
        if key in self._concepts:
            return self._concepts[key].get(tag)
        payload = self._concept_fetch(key, tag)
        if payload is not None and not concept_has_facts(payload):
            self.fallback_issuers.add(key)
            self._concepts[key] = self._concepts_loader(key) or {}
            return self._concepts[key].get(tag)
        return payload


def default_sec_fetcher(
    user_agent: str, *, timeout: float = SEC_TIMEOUT_SECONDS
) -> SecFallbackFetcher:
    """The live SEC fetcher: per-tag concepts with the ``companyfacts`` fallback."""
    concept_client = SecConceptClient(user_agent, timeout=timeout)
    facts_client = SecCompanyFactsClient(user_agent, timeout=timeout)
    return SecFallbackFetcher(concept_client.fetch, facts_client.concepts)


def default_yahoo_fetcher(
    ticker: str, fiscal_year: int, fiscal_year_end: date | None = None
) -> tuple[dict[str, float | None], date | None]:
    """Yahoo's figures for the fiscal-year column matching ``fiscal_year_end``.

    Best effort: an unavailable provider yields ``({}, None)`` and simply leaves
    Yahoo out of that company's comparison set. Prices are read, never written.
    """
    from backend.providers.yahoo.provider import YahooFinanceProvider

    provider = YahooFinanceProvider()
    index = 0
    period_end: date | None = None
    with contextlib.suppress(Exception):
        for position, entry in enumerate(provider.get_fiscal_year_end_dates(ticker)):
            candidate = _parse_date(entry.get("end_date"))
            if fiscal_year_end is not None and candidate == fiscal_year_end:
                index = position
                period_end = candidate
                break
            if position == 0:
                period_end = candidate
    financials = provider.get_financials(ticker, index)
    if financials is None:
        return {}, None
    values = {spec.metric: metric_value(financials, spec) for spec in AUDIT_METRICS}
    return values, period_end


def default_split_lookup(ticker: str, target_date: date | None) -> float | None:
    """The split multiplier that aligns ``target_date`` figures with today.

    Read-only and optional: any failure (offline, no history) means "no factor",
    which the classifier then simply skips. Prices are never persisted.
    """
    if target_date is None:
        return None
    try:
        from backend.services.price_service import get_price_service

        factor = get_price_service().get_split_adjustment(ticker, target_date)
    except Exception:  # noqa: BLE001 — a missing factor is not an audit failure
        return None
    if factor is None:
        return None
    factor = float(factor)
    return factor if factor > 0 and factor != 1.0 else None


# ---------------------------------------------------------------------------
# per-company audit
# ---------------------------------------------------------------------------
def audit_company(
    ticker: str,
    cik: str,
    *,
    repo: Any,
    sec_fetcher: Callable[[str, str], dict | None] | None = None,
    yahoo_fetcher: Callable[..., Any] | None = None,
    split_lookup: Callable[[str, date | None], float | None] | None = None,
    metrics: Sequence[MetricSpec] = AUDIT_METRICS,
) -> dict[str, Any]:
    """Compare one company across the sources. Read-only; never raises."""
    row: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "fiscal_year": None,
        "fiscal_year_end": None,
        "error": None,
        "comparisons": [],
    }
    try:
        fiscal_year = repo.get_latest_completed_fiscal_year(ticker)
        if fiscal_year is None:
            row["error"] = "no completed fiscal year"
            return row
        financials = repo.get_by_year(ticker, fiscal_year)
        if financials is None:
            row["error"] = "no fundamentals"
            return row

        period_a = repo.get_fiscal_year_end_date(ticker, fiscal_year)
        row["fiscal_year"] = fiscal_year
        row["fiscal_year_end"] = period_a.isoformat() if period_a else None

        sec_classes: dict[str, str] = {}
        if sec_fetcher is not None:
            sec_classes, sec_ok = _audit_sec_side(
                row,
                ticker=ticker,
                cik=cik,
                financials=financials,
                sec_fetcher=sec_fetcher,
                period_a=period_a,
                metrics=metrics,
            )
            if not sec_ok:
                # Not one tag returned a fact: EDGAR is unreachable, or the
                # issuer's concept endpoint is empty and the fallback failed
                # too. That is a source outage, never a database defect.
                row["comparisons"] = [
                    item
                    for item in row["comparisons"]
                    if item["source_b"] != "sec_edgar"
                ]
                row["error"] = "SEC EDGAR returned no data"
                sec_classes = {}
        if yahoo_fetcher is not None:
            _audit_yahoo_side(
                row,
                ticker=ticker,
                financials=financials,
                yahoo_fetcher=yahoo_fetcher,
                fiscal_year=fiscal_year,
                period_a=period_a,
                sec_classes=sec_classes,
                split_lookup=split_lookup,
                metrics=metrics,
            )
    except Exception as exc:  # noqa: BLE001 — one bad ticker must not abort the audit
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _audit_sec_side(
    row: dict[str, Any],
    *,
    ticker: str,
    cik: str,
    financials: Any,
    sec_fetcher: Callable[[str, str], dict | None],
    period_a: date | None,
    metrics: Sequence[MetricSpec],
) -> tuple[dict[str, str], bool]:
    """Financial-DataBase vs SEC: per-metric classes and whether SEC answered."""
    classes: dict[str, str] = {}
    payloads = 0

    def counted(cik: str, tag: str) -> dict | None:
        nonlocal payloads
        payload = sec_fetcher(cik, tag)
        if concept_has_facts(payload):
            payloads += 1
        return payload

    for spec in metrics:
        value_a = metric_value(financials, spec)
        if value_a is None:
            continue

        by_tag = sec_metric_facts(cik, spec, counted, period_a)
        tag, facts = _preferred(by_tag, period_a)
        if not facts:
            # No filing carries the line at all: a defect for a strict metric,
            # inconclusive for one filers may legitimately not tag.
            classification, reason = classify_comparison(
                value_a=value_a,
                value_b=None,
                tolerance_pct=spec.tolerance_pct,
                authoritative=True,
                upstream_available=False,
                strict=spec.strict,
            )
            row["comparisons"].append(
                comparison_row(
                    ticker=ticker,
                    metric=spec.metric,
                    source="sec_edgar",
                    value_a=value_a,
                    value_b=None,
                    classification=classification,
                    reason=reason,
                    period_a=period_a,
                )
            )
            classes[spec.metric] = classification
            continue

        chosen = facts[0]
        restated = [
            fact
            for fact in facts[1:]
            if fact.period_end == chosen.period_end
            and not _within_tolerance(fact.value, chosen.value, spec.tolerance_pct)
        ]
        classification, reason = classify_comparison(
            value_a=value_a,
            value_b=chosen.value,
            tolerance_pct=spec.tolerance_pct,
            period_a=period_a,
            period_b=chosen.period_end,
            authoritative=True,
            magnitude_only=spec.magnitude_only,
            alternative_tags={
                name: items for name, items in by_tag.items() if name != tag
            },
            restated=restated,
        )
        row["comparisons"].append(
            comparison_row(
                ticker=ticker,
                metric=spec.metric,
                source="sec_edgar",
                value_a=value_a,
                value_b=chosen.value,
                classification=classification,
                reason=f"{reason} [tag {tag}]",
                period_a=period_a,
                period_b=chosen.period_end,
            )
        )
        classes[spec.metric] = classification
    return classes, payloads > 0


def _audit_yahoo_side(
    row: dict[str, Any],
    *,
    ticker: str,
    financials: Any,
    yahoo_fetcher: Callable[..., Any],
    fiscal_year: int,
    period_a: date | None,
    sec_classes: Mapping[str, str],
    split_lookup: Callable[[str, date | None], float | None] | None,
    metrics: Sequence[MetricSpec],
) -> None:
    """Financial-DataBase vs Yahoo. Yahoo is never authoritative."""
    try:
        values, period_b = yahoo_fetcher(ticker, fiscal_year, period_a)
    except Exception:  # noqa: BLE001 — Yahoo is optional
        return
    if not values:
        return

    # One split lookup per company, only when a share-count metric is compared.
    split_factor: float | None = None
    if split_lookup is not None:
        with contextlib.suppress(Exception):
            split_factor = split_lookup(ticker, period_a)

    for spec in metrics:
        value_a = metric_value(financials, spec)
        value_b = values.get(spec.metric)
        if value_a is None or value_b is None:
            continue
        confirmed = sec_classes.get(spec.metric) in {
            MATCH,
            DIFFERENT_PERIOD,
            DIFFERENT_TAG,
            SPLIT_ADJUSTMENT,
            RESTATEMENT,
        }
        classification, reason = classify_comparison(
            value_a=value_a,
            value_b=value_b,
            tolerance_pct=spec.tolerance_pct,
            period_a=period_a,
            period_b=period_b,
            authoritative=False,
            magnitude_only=spec.magnitude_only,
            split_factor=split_factor
            if spec.metric in {"shares_outstanding", "eps_diluted"}
            else None,
            authoritative_agrees=confirmed if sec_classes else None,
        )
        row["comparisons"].append(
            comparison_row(
                ticker=ticker,
                metric=spec.metric,
                source="yahoo_finance",
                value_a=value_a,
                value_b=value_b,
                classification=classification,
                reason=reason,
                period_a=period_a,
                period_b=period_b,
            )
        )


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
CSV_COLUMNS = (
    "ticker",
    "metric",
    "source_a",
    "source_b",
    "value_a",
    "value_b",
    "delta_pct",
    "classification",
)


def metric_catalogue(metrics: Sequence[MetricSpec]) -> list[dict[str, Any]]:
    """The audited metrics, their tolerances and formulas (report metadata)."""
    catalogue: list[dict[str, Any]] = []
    for spec in metrics:
        entry: dict[str, Any] = {
            "metric": spec.metric,
            "tolerance_pct": spec.tolerance_pct,
            "tags": list(spec.tags),
        }
        if spec.derive is not None:
            entry["formula"] = DERIVATIONS[spec.derive][0]
        catalogue.append(entry)
    return catalogue


def build_report(
    companies: Sequence[tuple[str, str]],
    *,
    repo: Any,
    sec_fetcher: Callable[[str, str], dict | None] | None = None,
    yahoo_fetcher: Callable[..., Any] | None = None,
    split_lookup: Callable[[str, date | None], float | None] | None = None,
    metrics: Sequence[MetricSpec] = AUDIT_METRICS,
    seed: int = DEFAULT_SEED,
    sample_size: int | None = None,
    requested_sources: Sequence[str] = ("sec", "yahoo"),
    skipped_sources: Mapping[str, str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run the audit over ``companies`` and return the report payload.

    Deterministic: with the same companies, fetchers and ``generated_at`` the
    payload (and therefore the JSON and CSV) is byte-identical.
    """
    rows = [
        audit_company(
            ticker,
            cik,
            repo=repo,
            sec_fetcher=sec_fetcher,
            yahoo_fetcher=yahoo_fetcher,
            split_lookup=split_lookup,
            metrics=metrics,
        )
        for ticker, cik in companies
    ]

    comparisons = [item for row in rows for item in row["comparisons"]]
    breakdown: dict[str, int] = {}
    for item in comparisons:
        key = item["classification"]
        breakdown[key] = breakdown.get(key, 0) + 1

    summary = {
        "tickers": len(rows),
        "with_fundamentals": sum(1 for row in rows if row["error"] is None),
        "errors": sum(1 for row in rows if row["error"] is not None),
        "comparisons": len(comparisons),
        "skipped": breakdown.get(SKIPPED, 0),
        "by_classification": dict(sorted(breakdown.items())),
        "expected": sum(count for key, count in breakdown.items() if key in EXPECTED),
        "data_error_fdb": breakdown.get(DATA_ERROR_FDB, 0),
        "data_error_external": breakdown.get(DATA_ERROR_EXTERNAL, 0),
        "unclassified": breakdown.get(UNCLASSIFIED, 0),
        "sec_tickers": sum(
            1
            for row in rows
            if any(item["source_b"] == "sec_edgar" for item in row["comparisons"])
        ),
        "yahoo_tickers": sum(
            1
            for row in rows
            if any(item["source_b"] == "yahoo_finance" for item in row["comparisons"])
        ),
    }

    return {
        "generated_at": generated_at
        or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample_size": len(rows) if sample_size is None else sample_size,
        "seed": seed,
        "requested_sources": list(requested_sources),
        "skipped_sources": dict(skipped_sources or {}),
        "period_match_days": PERIOD_MATCH_DAYS,
        "period_shift_days": PERIOD_SHIFT_DAYS,
        "metrics": metric_catalogue(metrics),
        "actions": dict(sorted(ACTIONS.items())),
        "notes": [],
        "tickers": rows,
        "summary": summary,
    }


def _format_quantity(value: Any) -> str:
    """Render a number with thousands separators, or ``N/A``."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def flagged(comparisons: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The comparisons a human must read: everything that is not MATCH/SKIPPED."""
    return [
        item for item in comparisons if item["classification"] not in {MATCH, SKIPPED}
    ]


def format_report(report: Mapping[str, Any]) -> str:
    """Render the human-readable report (the ``.log`` payload)."""
    summary = report["summary"]
    lines = [
        f"Data-quality audit {report['generated_at']}",
        (
            f"Sample: {report['sample_size']} (seed {report['seed']}), "
            f"sources: {', '.join(report['requested_sources'])}, "
            f"period match window: {report['period_match_days']} days"
        ),
    ]
    for source, reason in (report.get("skipped_sources") or {}).items():
        lines.append(f"Skipped source: {source} - {reason}")
    for note in report.get("notes") or ():
        lines.append(f"Note: {note}")
    lines.append("")

    for row in report["tickers"]:
        header = f"{row['ticker']} (CIK {row['cik']})"
        if row["fiscal_year"]:
            header += f" FY{row['fiscal_year']}"
        if row["fiscal_year_end"]:
            header += f" (end {row['fiscal_year_end']})"
        lines.append(header)
        if row["error"]:
            lines.append(f"  ERROR: {row['error']}")
            continue
        items = flagged(row["comparisons"])
        if not items:
            lines.append("  all comparisons within tolerance")
            continue
        for item in items:
            difference = item["delta_pct"]
            delta_text = f"{difference:.2f}%" if difference is not None else "n/a"
            lines.append(
                f"  {item['classification']:<20} {item['metric']:<22} "
                f"{item['source_b']:<14} db={_format_quantity(item['value_a'])} "
                f"ext={_format_quantity(item['value_b'])} d={delta_text}"
            )
            lines.append(f"      action: {item['action']} - {item['reason']}")

    lines.append("")
    lines.append("By classification:")
    if not summary["by_classification"]:
        lines.append("  (no comparisons)")
    for name, count in summary["by_classification"].items():
        lines.append(f"  {name:<20} {count}")
    lines.append("")
    lines.append(
        "Summary: "
        f"tickers={summary['tickers']} "
        f"fundamentals={summary['with_fundamentals']} "
        f"errors={summary['errors']} "
        f"comparisons={summary['comparisons']} "
        f"skipped={summary['skipped']} "
        f"expected={summary['expected']} "
        f"data_error_fdb={summary['data_error_fdb']} "
        f"data_error_external={summary['data_error_external']} "
        f"unclassified={summary['unclassified']} "
        f"sec={summary['sec_tickers']} "
        f"yahoo={summary['yahoo_tickers']}"
    )
    return "\n".join(lines) + "\n"


def write_reports(
    report: Mapping[str, Any],
    out_dir: Path | str = DEFAULT_OUT_DIR,
    *,
    when: date | None = None,
) -> tuple[Path, Path, Path]:
    """Write the ``.log``, ``.json`` and ``.csv`` reports; return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    day = (when or datetime.now(UTC).date()).isoformat()
    log_path = out_dir / f"audit_data_quality_{day}.log"
    json_path = out_dir / f"audit_data_quality_{day}.json"
    csv_path = out_dir / f"audit_data_quality_{day}.csv"

    log_path.write_text(format_report(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in report["tickers"]:
            for item in row["comparisons"]:
                if item["classification"] == SKIPPED:
                    continue
                writer.writerow(item)
    return log_path, json_path, csv_path


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def load_universe_map(path: Path | str = DEFAULT_UNIVERSE) -> dict[str, str]:
    """``{ticker: cik}`` for every universe row that names a CIK."""
    path = Path(path)
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("ticker") or "").strip().upper()
            cik = (row.get("cik") or "").strip()
            if ticker and cik:
                mapping[ticker] = cik
    return mapping


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-source data-quality audit (Financial-DataBase vs SEC EDGAR "
            "and Yahoo Finance) with classified discrepancies."
        )
    )
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers instead of a universe sample",
    )
    parser.add_argument(
        "--sources",
        default=DEFAULT_SOURCES,
        help=f"Comma-separated sources to compare ({', '.join(SUPPORTED_SOURCES)})",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--timeout", type=float, default=SEC_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def _resolve_tickers(
    requested: str, universe_path: str
) -> tuple[list[tuple[str, str]], list[str]]:
    """Resolve ``--tickers`` against the universe file. Returns (pairs, missing)."""
    mapping: dict[str, str] = {}
    for row in load_sp500_universe(universe_path):
        mapping[row[0]] = row[1]
    with (
        contextlib.suppress(OSError),
        open(universe_path, encoding="utf-8", newline="") as handle,
    ):
        for row in csv.DictReader(handle):
            ticker = (row.get("ticker") or "").strip().upper()
            cik = (row.get("cik") or "").strip()
            if ticker and cik:
                mapping.setdefault(ticker, cik)

    pairs: list[tuple[str, str]] = []
    missing: list[str] = []
    for token in requested.split(","):
        ticker = token.strip().upper()
        if not ticker:
            continue
        cik = mapping.get(ticker)
        if cik:
            pairs.append((ticker, cik))
        else:
            missing.append(ticker)
    return sorted(set(pairs)), sorted(set(missing))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the audit and return the process exit code."""
    args = _parse_args(argv)
    with contextlib.suppress(Exception):  # dotenv is optional; env may be set
        from dotenv import load_dotenv

        load_dotenv()

    requested = [
        token.strip().lower() for token in args.sources.split(",") if token.strip()
    ]
    unknown = [
        source
        for source in requested
        if source not in SUPPORTED_SOURCES and source not in SKIPPED_SOURCES
    ]
    if unknown:
        print(f"error: unknown source(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    skipped_sources = {
        source: SKIPPED_SOURCES[source]
        for source in requested
        if source in SKIPPED_SOURCES
    }
    use_sec = "sec" in requested
    use_yahoo = "yahoo" in requested
    if not use_sec and not use_yahoo:
        print("error: no comparable source requested", file=sys.stderr)
        return 2

    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )

    repo = FinancialDatabaseRepository()
    if not repo.available():
        print("error: Financial-DataBase is not reachable", file=sys.stderr)
        return 2

    missing: list[str] = []
    if args.tickers:
        companies, missing = _resolve_tickers(args.tickers, args.universe)
        for ticker in missing:
            print(f"warning: {ticker} is not in {args.universe}", file=sys.stderr)
        if not companies:
            print("error: no requested ticker could be resolved", file=sys.stderr)
            return 2
    else:
        universe = load_sp500_universe(args.universe)
        if not universe:
            print(
                f"error: no S&P 500 tickers found in {args.universe}", file=sys.stderr
            )
            return 2
        companies = sorted(choose_sample(universe, args.sample, args.seed))

    sec_fetcher = None
    if use_sec:
        user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
        if not user_agent:
            print("error: SEC_USER_AGENT is not set", file=sys.stderr)
            return 2
        sec_fetcher = default_sec_fetcher(user_agent, timeout=args.timeout)

    report = build_report(
        companies,
        repo=repo,
        sec_fetcher=sec_fetcher,
        yahoo_fetcher=default_yahoo_fetcher if use_yahoo else None,
        split_lookup=default_split_lookup if use_yahoo else None,
        seed=args.seed,
        sample_size=len(companies),
        requested_sources=["financial_database", *requested],
        skipped_sources=skipped_sources,
    )
    fallback_issuers = sorted(getattr(sec_fetcher, "fallback_issuers", ()))
    if fallback_issuers:
        report["notes"].append(
            "companyconcept returned an empty envelope for "
            f"{len(fallback_issuers)} issuer(s); companyfacts was used instead: "
            + ", ".join(fallback_issuers)
        )
    log_path, json_path, csv_path = write_reports(report, args.out)
    print(format_report(report), end="")
    print(f"wrote {log_path}, {json_path} and {csv_path}")

    summary = report["summary"]
    if use_sec and summary["sec_tickers"] == 0:
        print("error: SEC EDGAR could not be reached for any ticker", file=sys.stderr)
        return 2
    return 1 if summary["data_error_fdb"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
