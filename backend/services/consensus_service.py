"""Consensus rankings: aggregate the eight methodology verdicts per company.

Reads the precomputed JSON written by ``scripts/compute_consensus_rankings``
(weekly model, see ``docs/consensus_screener.md``). Pure aggregation over a
local file: no LLM, no network, no database, no prices.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: Output schema version written by the computation script.
CONSENSUS_VERSION = 1
#: A file older than this is refused (stale rankings mislead).
STALE_AFTER_DAYS = 30
#: The six Lynch buckets shown on the page, in canonical order.
LYNCH_CATEGORIES = (
    "SLOW_GROWER",
    "STALWART",
    "FAST_GROWER",
    "CYCLICAL",
    "TURNAROUND",
    "ASSET_PLAY",
)


@dataclass(frozen=True)
class CompanyConsensus:
    """One company's aggregated verdicts across the methodologies."""

    ticker: str
    name: str
    lynch_category: str
    verdicts: dict[str, str]
    buy_count: int
    avoid_count: int
    insufficient_count: int
    consensus_score: int

    @property
    def is_data_hole(self) -> bool:
        """True when every methodology said INSUFFICIENT_DATA."""
        return bool(self.verdicts) and self.insufficient_count == len(self.verdicts)


@dataclass
class ConsensusReport:
    """A loaded consensus file."""

    date: str
    universe: str
    companies: list[CompanyConsensus]


def default_consensus_dir() -> Path:
    """``data/demo/consensus`` in demo mode, ``data/consensus`` otherwise."""
    from backend.services.demo_mode import DEMO_ROOT, is_demo

    return DEMO_ROOT / "consensus" if is_demo() else Path("data/consensus")


class ConsensusService:
    """Loads one consensus report and derives the screener rankings.

    Call :meth:`load_latest` or :meth:`load_by_date` first; the ranking
    helpers operate on the loaded report and return empty results while no
    report is loaded.
    """

    def __init__(
        self,
        directory: Path | str | None = None,
        max_age_days: int = STALE_AFTER_DAYS,
    ) -> None:
        self._dir = (
            Path(directory) if directory is not None else default_consensus_dir()
        )
        self._max_age_days = max_age_days
        self._report: ConsensusReport | None = None

    # ------------------------------------------------------------------
    # loading
    # ------------------------------------------------------------------
    def load_latest(self) -> ConsensusReport | None:
        """Newest ``consensus_*.json``; None (with a warning) when missing/stale."""
        files = sorted(self._dir.glob("consensus_*.json"))
        if not files:
            logger.warning("no consensus file found in %s", self._dir)
            self._report = None
            return None
        report = self._read(files[-1])
        if report is None:
            self._report = None
            return None
        try:
            report_date = date.fromisoformat(report.date)
        except ValueError:
            logger.warning(
                "consensus file %s has an invalid date %r", files[-1].name, report.date
            )
            self._report = None
            return None
        age = (datetime.now(UTC).date() - report_date).days
        if age > self._max_age_days:
            logger.warning(
                "consensus file %s is stale (%s days old)", files[-1].name, age
            )
            self._report = None
            return None
        self._report = report
        return report

    def load_by_date(self, date_str: str) -> ConsensusReport | None:
        """Load ``consensus_<date>.json``; None (with a warning) when absent."""
        report = self._read(self._dir / f"consensus_{date_str}.json")
        self._report = report
        return report

    def _read(self, path: Path) -> ConsensusReport | None:
        if not path.exists():
            logger.warning("consensus file not found: %s", path)
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("consensus file unreadable: %s", path)
            return None
        companies: list[CompanyConsensus] = []
        for ticker, row in sorted((payload.get("companies") or {}).items()):
            verdicts = {
                str(key): str(value)
                for key, value in (row.get("verdicts") or {}).items()
            }
            companies.append(
                CompanyConsensus(
                    ticker=ticker,
                    name=str(row.get("name") or ticker),
                    lynch_category=str(row.get("lynch_category") or "UNKNOWN"),
                    verdicts=verdicts,
                    buy_count=int(row.get("buy_count") or 0),
                    avoid_count=int(row.get("avoid_count") or 0),
                    insufficient_count=int(row.get("insufficient_count") or 0),
                    consensus_score=int(row.get("consensus_score") or 0),
                )
            )
        return ConsensusReport(
            date=str(payload.get("date") or ""),
            universe=str(payload.get("universe") or ""),
            companies=companies,
        )

    # ------------------------------------------------------------------
    # rankings
    # ------------------------------------------------------------------
    @staticmethod
    def _rank_key(company: CompanyConsensus) -> tuple:
        return (
            -company.buy_count,
            -company.consensus_score,
            company.avoid_count,
            company.ticker,
        )

    def _ranked(self) -> list[CompanyConsensus]:
        """Rankable companies (all-INSUFFICIENT data holes excluded)."""
        if self._report is None:
            return []
        return sorted(
            (c for c in self._report.companies if not c.is_data_hole),
            key=self._rank_key,
        )

    def top_by_consensus(self, n: int = 20) -> list[CompanyConsensus]:
        """Highest-conviction companies: most BUYs, then score."""
        return self._ranked()[: max(n, 0)]

    def best_per_lynch_category(
        self, per_category: int = 5
    ) -> dict[str, list[CompanyConsensus]]:
        """Top ``per_category`` companies for each of the six Lynch buckets."""
        grouped: dict[str, list[CompanyConsensus]] = {
            category: [] for category in LYNCH_CATEGORIES
        }
        for company in self._ranked():
            bucket = grouped.setdefault(company.lynch_category, [])
            if len(bucket) < per_category:
                bucket.append(company)
        return grouped

    def disagreement_zone(
        self,
        min_buy: int = 3,
        max_buy: int = 5,
        min_avoid: int = 3,
        max_avoid: int = 5,
    ) -> list[CompanyConsensus]:
        """Companies where the BUY and AVOID camps are both significant."""
        return [
            company
            for company in self._ranked()
            if min_buy <= company.buy_count <= max_buy
            and min_avoid <= company.avoid_count <= max_avoid
        ]

    def verdict_matrix(self) -> list[dict[str, str]]:
        """One row per company with one column per methodology (UI heatmap)."""
        rows = []
        for company in self._ranked():
            row = {"Ticker": company.ticker, "Name": company.name}
            row.update(company.verdicts)
            rows.append(row)
        return rows
