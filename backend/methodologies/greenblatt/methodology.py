"""Greenblatt Magic Formula as a book methodology (cross-sectional).

The Magic Formula ranks a whole universe by return on capital and earnings
yield; a single-ticker evaluation can only look up a pre-computed ranking.
``scripts/compute_greenblatt_rankings.py`` writes
``data/rankings/greenblatt_<date>.json`` (recommended: weekly), and this
methodology reads the newest file, looks the ticker up and maps its
percentile to a verdict. It never touches the network or a database: the
only input besides the injected row is the ranking file.

Verdict by percentile (lower is better): <= 0.10 BUY, <= 0.30 WATCH,
<= 0.50 HOLD, otherwise AVOID. Financial companies abstain (the ROC
denominator assumes an industrial balance sheet).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from backend.methodologies.base import (
    FINANCIAL_NA_REASON,
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
)
from backend.methodologies.greenblatt.rules import ALL_RULES, RULE_3_RANK

#: Where the weekly ranking files live (relative to the repo root).
RANKINGS_DIR = Path("data/rankings")
#: A ranking file older than this is considered stale. The systemd timer
#: (deploy/systemd/greenblatt-rankings.timer) refreshes the file weekly, so
#: two missed runs (14 days) mean something is broken.
STALE_DAYS = 14
#: Percentile upper bounds per verdict (lower percentile = better).
_BUY_PERCENTILE = 0.10
_WATCH_PERCENTILE = 0.30
_HOLD_PERCENTILE = 0.50


class GreenblattMethodology(Methodology):
    """Look up the pre-computed Magic Formula rank for one ticker."""

    name = "greenblatt"
    version = "1.0.0"
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

        payload, error = self._load_rankings()
        if payload is None:
            return self._insufficient(ticker, error)

        entry = (payload.get("rankings") or {}).get(ticker.upper())
        if entry is None:
            return self._insufficient(
                ticker,
                (
                    "ticker not in the Greenblatt ranking "
                    "(run scripts/compute_greenblatt_rankings.py)"
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

        percentile = entry.get("percentile")
        verdict = self._verdict_for(percentile)
        score = (
            round((1.0 - float(percentile)) * 100.0, 2)
            if percentile is not None
            else None
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
                f"(percentile {percentile:.1%}); ranking date "
                f"{payload.get('date')}."
            ),
            f"verdict: {verdict.value}",
        ]
        passed = ["greenblatt.rule_1_roc", "greenblatt.rule_2_earnings_yield"]
        failed: list[str] = []
        if verdict is Verdict.AVOID:
            failed.append(RULE_3_RANK.id)
        else:
            passed.append(RULE_3_RANK.id)
        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=metrics,
            reasons=reasons,
            red_flags=[],
            confidence=Confidence.HIGH,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=passed,
            failed_rules=failed,
        )

    def rules(self) -> list:
        return list(ALL_RULES)

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.name,
            "version": self.version,
            "family": self.family,
            "source": "The Little Book That Beats the Market (2005)",
            "known_limitations": [
                (
                    "cross-sectional: requires the weekly ranking file from "
                    "scripts/compute_greenblatt_rankings.py; missing or stale "
                    "files return INSUFFICIENT_DATA"
                ),
                (
                    "does not apply to financials (the ROC denominator assumes "
                    "an industrial balance sheet)"
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
    def _verdict_for(percentile: float | None) -> Verdict:
        if percentile is None:
            return Verdict.INSUFFICIENT_DATA
        if percentile <= _BUY_PERCENTILE:
            return Verdict.BUY
        if percentile <= _WATCH_PERCENTILE:
            return Verdict.WATCH
        if percentile <= _HOLD_PERCENTILE:
            return Verdict.HOLD
        return Verdict.AVOID

    def _load_rankings(self) -> tuple[dict | None, str | None]:
        """Newest ranking payload, or (None, reason) when unusable."""
        directory = self._rankings_dir
        # Demo mode: the pinned offline bundle, only when the default dir is
        # in use (an explicit dir — tests, custom runs — is respected).
        from backend.services.demo_mode import demo_rankings_dir, is_demo

        if is_demo() and directory == RANKINGS_DIR:
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
        if age_days > STALE_DAYS:
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
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[],
            failed_rules=[],
        )
