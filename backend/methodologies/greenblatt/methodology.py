"""Greenblatt Magic Formula as a book methodology (cross-sectional).

The Magic Formula ranks a whole universe by return on capital and earnings
yield; a single-ticker evaluation can only look up a pre-computed ranking.
``scripts/compute_greenblatt_rankings.py`` writes
``data/rankings/greenblatt_<date>.json`` (recommended: weekly), and this
methodology reads the newest file, looks the ticker up and evaluates a weighted
overlay around that rank. It never touches the network or a database: the only
inputs besides the injected rows are the ranking file and a price-free market-cap
derivation.

**The ranking remains the primary input.** The overlay never recomputes the
cross-sectional ranking; it decomposes the rank into explicit ROC, earnings-
yield and quality checks so the verdict is transparent:

    weighted_score = sum(passed weight) / sum(evaluable weight)

Thresholds: BUY >= 0.85, WATCH >= 0.70, HOLD >= 0.50, else AVOID. More than
30% of the weighted rules missing data returns INSUFFICIENT_DATA.

This replaces the old percentile cut (top 10% BUY / top 30% WATCH / top 50%
HOLD) as the *source* of the verdict. The ranking checks (in file, top 50,
top 100) are the largest single block of weight and a top-50 rank is the
normal path to BUY, but a top-10% company with failing quality checks is no
longer automatically a BUY, and a bottom-half company with clean fundamentals
lands in HOLD rather than AVOID.

Financial companies and REITs abstain (the ROC denominator assumes an
industrial balance sheet), and tickers outside the S&P 500 ranking universe
return NOT_APPLICABLE.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.methodologies.base import (
    FINANCIAL_NA_REASON,
    REIT_NA_REASON,
    UNIVERSE_NA_REASON,
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
    is_reit,
)
from backend.methodologies.common.weighted import weighted_verdict
from backend.methodologies.greenblatt.deep_checks import (
    CATEGORIES as DEEP_CATEGORIES,
)
from backend.methodologies.greenblatt.deep_checks import CHECKS as DEEP_CHECKS
from backend.methodologies.greenblatt.deep_checks import run_checks
from backend.methodologies.greenblatt.rules import ALL_RULES, RULE_3_RANK

#: Where the weekly ranking files live (relative to the repo root).
RANKINGS_DIR = Path("data/rankings")
#: A ranking file older than this is considered stale. The systemd timer
#: (deploy/systemd/greenblatt-rankings.timer) refreshes the file weekly, so
#: two missed runs (14 days) mean something is broken.
STALE_DAYS = 14
#: Percentile below which the legacy combined-rank rule is reported as passed.
#: Kept only for the reporting-only rule id; it no longer drives the verdict.
_LEGACY_RANK_PERCENTILE = 0.50
#: Master universe file, used to tell "not ranked because outside the ranking
#: universe" (N/A) from "ranked universe but inputs missing" (INSUFFICIENT).
_UNIVERSE_PATH = Path(__file__).resolve().parents[3] / "config" / "universe.csv"

#: Weighted-score thresholds (shared with the other deep methodologies).
BUY_THRESHOLD = 0.85
WATCH_THRESHOLD = 0.70
HOLD_THRESHOLD = 0.50

#: Share of missing weight above which the verdict is INSUFFICIENT_DATA.
MAX_MISSING_WEIGHT = 0.30


@lru_cache(maxsize=1)
def _universe_source_index() -> dict[str, str]:
    """Ticker -> source_index labels from the master universe (empty if absent)."""
    try:
        with _UNIVERSE_PATH.open(encoding="utf-8") as handle:
            return {
                (row.get("ticker") or "").strip().upper(): (
                    row.get("source_index") or ""
                ).upper()
                for row in csv.DictReader(handle)
                if (row.get("ticker") or "").strip()
            }
    except OSError:
        return {}


class GreenblattMethodology(Methodology):
    """Look up the pre-computed Magic Formula rank and weigh its overlay."""

    name = "greenblatt"
    version = "2.0.0"
    family = "MAGIC_FORMULA"

    def __init__(self, rankings_dir: Path | str | None = None) -> None:
        self._rankings_dir = Path(rankings_dir) if rankings_dir else RANKINGS_DIR

    # ------------------------------------------------------------------
    # Methodology ABC
    # ------------------------------------------------------------------
    def evaluate(
        self, ticker: str, fundamentals: Any, prices: Any
    ) -> MethodologyResult:
        rows = [row for row in (fundamentals or []) if row is not None]
        latest = rows[0] if rows else None

        if is_financial(latest, getattr(latest, "sector", None)):
            na_reason = financial_na_reason(
                latest, rows, getattr(latest, "sector", None), ticker
            )
            return self._insufficient(
                ticker,
                (
                    "Greenblatt Magic Formula does not apply to financial "
                    "companies (banks, insurers): the ROC denominator assumes "
                    "an industrial balance sheet."
                ),
                verdict=Verdict.NOT_APPLICABLE,
                na_reason=na_reason,
            )

        # REITs report FFO and present unclassified balance sheets, so net
        # working capital and net PPE are not comparable with industrials.
        if is_reit(getattr(latest, "sector", None), getattr(latest, "industry", None)):
            return self._insufficient(
                ticker,
                (
                    "Greenblatt Magic Formula does not apply to REITs: the ROC "
                    "denominator assumes a classified industrial balance sheet."
                ),
                verdict=Verdict.NOT_APPLICABLE,
                na_reason=REIT_NA_REASON,
            )

        payload, error = self._load_rankings()
        if payload is None:
            return self._insufficient(ticker, error)

        entry = (payload.get("rankings") or {}).get(ticker.upper())
        if entry is None:
            sources = _universe_source_index().get(ticker.upper())
            if sources is not None and "SP500" not in sources:
                return self._insufficient(
                    ticker,
                    (
                        "Greenblatt Magic Formula only ranks S&P 500 "
                        f"constituents (source indices: {sources or 'none'})."
                    ),
                    verdict=Verdict.NOT_APPLICABLE,
                    na_reason=UNIVERSE_NA_REASON,
                )
            return self._insufficient(
                ticker,
                (
                    "Ticker is in the universe but missing from the latest "
                    "Greenblatt ranking. Regenerate it with "
                    "scripts/compute_greenblatt_rankings.py."
                ),
            )

        roc = entry.get("roc")
        earnings_yield = entry.get("earnings_yield")
        if roc is None or roc <= 0:
            return self._insufficient(
                ticker, "return on capital is not positive in the ranking"
            )
        if earnings_yield is None or earnings_yield <= 0:
            return self._insufficient(
                ticker, "earnings yield is not positive in the ranking"
            )
        if entry.get("combined_rank") is None:
            return self._insufficient(
                ticker, "combined rank missing from the ranking file"
            )

        results = run_checks(rows, entry)
        verdict, score, confidence = weighted_verdict(results)

        percentile = entry.get("percentile")
        percentile_text = (
            f"{float(percentile):.1%}" if percentile is not None else "n/a"
        )
        metrics = {
            "roc": roc,
            "earnings_yield": earnings_yield,
            "rank_roc": entry.get("rank_roc"),
            "rank_ey": entry.get("rank_ey"),
            "combined_rank": entry.get("combined_rank"),
            "percentile": percentile,
            "ranking_date": payload.get("date"),
            "universe_size": payload.get("universe_size"),
            "fiscal_year": entry.get("fiscal_year"),
        }
        for result in results:
            metrics[result.rule_id.replace("greenblatt.", "")] = result.value

        reasons = [
            (
                f"ROC {roc:.1%}: EBIT / (net working capital + net PPE), "
                f"rank {entry.get('rank_roc')} of {payload.get('universe_size')}."
            ),
            (
                f"Earnings yield {earnings_yield:.1%}: EBIT / enterprise "
                f"value, rank {entry.get('rank_ey')} of "
                f"{payload.get('universe_size')}."
            ),
            (
                f"Combined rank {entry.get('combined_rank')} "
                f"(percentile {percentile_text}); ranking date "
                f"{payload.get('date')}."
            ),
        ]
        for result in results:
            mark = (
                "PASS"
                if result.passed is True
                else "FAIL"
                if result.passed is False
                else "N/A"
            )
            weight = "" if result.weight == 0 else f" x{result.weight}"
            reasons.append(f"[{mark}]{weight} {result.detail}")
        reasons.append(f"verdict: {verdict.value}")

        passed_rules = [result.rule_id for result in results if result.passed is True]
        failed_rules = [result.rule_id for result in results if result.passed is False]
        # The original explicit rules stay visible for compatibility; they are
        # reporting-only and are not double-counted in the weighted score.
        passed_rules.extend(
            ["greenblatt.rule_1_roc", "greenblatt.rule_2_earnings_yield"]
        )
        if percentile is not None and float(percentile) <= _LEGACY_RANK_PERCENTILE:
            passed_rules.append(RULE_3_RANK.id)
        else:
            failed_rules.append(RULE_3_RANK.id)

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=metrics,
            reasons=reasons,
            red_flags=[
                f"{result.name}: {result.detail}"
                for result in results
                if result.passed is False
            ],
            confidence=confidence,
            sources=self._sources(),
            passed_rules=passed_rules,
            failed_rules=failed_rules,
        )

    def rules(self) -> list:
        return list(ALL_RULES) + [check.rule() for check in DEEP_CHECKS]

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.name,
            "version": self.version,
            "family": self.family,
            "source": "The Little Book That Beats the Market (2005)",
            "categories": list(DEEP_CATEGORIES),
            "thresholds": {
                "buy": BUY_THRESHOLD,
                "watch": WATCH_THRESHOLD,
                "hold": HOLD_THRESHOLD,
                "max_missing_weight": MAX_MISSING_WEIGHT,
            },
            "known_limitations": [
                (
                    "cross-sectional: requires the weekly ranking file from "
                    "scripts/compute_greenblatt_rankings.py; missing or stale "
                    "files return INSUFFICIENT_DATA"
                ),
                (
                    "the ranking remains the primary input; the weighted "
                    "overlay only decomposes the rank and does not recompute "
                    "the universe"
                ),
                (
                    "the book was not available, so every rule is a public-"
                    "knowledge approximation, not a page citation"
                ),
                (
                    "market cap is derived from the ranking's earnings yield "
                    "(EV = EBIT / EY) because the ranking payload has no "
                    "market-cap field"
                ),
                (
                    "does not apply to financials (the ROC denominator assumes "
                    "an industrial balance sheet) or REITs"
                ),
                (
                    "net fixed assets use the net PPE tag; filers without it "
                    "are excluded from the ranking"
                ),
            ],
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sources():
        return [rule.source for rule in ALL_RULES] + [
            check.source for check in DEEP_CHECKS
        ]

    def _load_rankings(self) -> tuple[dict | None, str | None]:
        """Newest ranking payload, or (None, reason) when unusable."""
        directory = self._rankings_dir
        # Demo mode: the pinned offline bundle, only when the default dir is
        # in use (an explicit dir — tests, custom runs — is respected).
        from backend.services.demo_mode import demo_rankings_dir, is_demo

        demo = is_demo() and directory == RANKINGS_DIR
        if demo:
            directory = demo_rankings_dir()
        if not directory.exists():
            return None, (
                "no Greenblatt ranking file "
                "(run scripts/compute_greenblatt_rankings.py)"
            )
        files = sorted(directory.glob("greenblatt_*.json"))
        if not files:
            return None, (
                "no Greenblatt ranking file "
                "(run scripts/compute_greenblatt_rankings.py)"
            )
        path = files[-1]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, f"Greenblatt ranking file {path.name} is unreadable"
        ranking_date = payload.get("date")
        if not ranking_date:
            return None, f"Greenblatt ranking file {path.name} has no date"
        try:
            age_days = (
                datetime.now(UTC).date() - date.fromisoformat(ranking_date)
            ).days
        except ValueError:
            return None, f"Greenblatt ranking file {path.name} has a bad date"
        if age_days > STALE_DAYS and not demo:
            return None, (
                f"Greenblatt rankings are stale ({age_days} days old); re-run "
                "scripts/compute_greenblatt_rankings.py"
            )
        return payload, None

    def _insufficient(
        self,
        ticker: str,
        reason: str,
        verdict: Verdict = Verdict.INSUFFICIENT_DATA,
        na_reason: str | None = None,
    ) -> MethodologyResult:
        reasons = [reason]
        if verdict is Verdict.NOT_APPLICABLE:
            reasons.insert(
                0, na_reason if na_reason is not None else FINANCIAL_NA_REASON
            )
        reasons.append(f"verdict: {verdict.value}")
        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=None,
            metrics={"financial_company": True} if "financial" in reason else {},
            reasons=reasons,
            red_flags=[],
            confidence=Confidence.HIGH,
            sources=self._sources(),
            passed_rules=[],
            failed_rules=[],
        )
