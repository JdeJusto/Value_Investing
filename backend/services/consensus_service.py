"""Consensus rankings: aggregate the eight methodology verdicts per company.

Reads the precomputed JSON written by ``scripts/compute_consensus_rankings``
(weekly model, see ``docs/consensus_screener.md``). Pure aggregation over a
local file: no LLM, no network, no database, no prices.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: Output schema version written by the computation script.
#: v1 = verdicts only; v2 adds ``prices_available`` / ``prices_snapshot``.
CONSENSUS_VERSION = 2
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

#: Human label prefixes (lynch_garp CATEGORY_LABELS) -> canonical key. Older
#: consensus files stored the label; the service normalizes them on read.
_CATEGORY_LABEL_PREFIXES = {
    "slow grower": "SLOW_GROWER",
    "stalwart": "STALWART",
    "fast grower": "FAST_GROWER",
    "cyclical": "CYCLICAL",
    "turnaround": "TURNAROUND",
    "asset play": "ASSET_PLAY",
}


def normalize_lynch_category(value: str) -> str:
    """Map a stored category (canonical key or human label) to a key."""
    if value.strip().upper().replace(" ", "_") in LYNCH_CATEGORIES:
        return value.strip().upper().replace(" ", "_")
    lowered = value.strip().lower()
    for prefix, category in _CATEGORY_LABEL_PREFIXES.items():
        if lowered.startswith(prefix):
            return category
    return "UNKNOWN"


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
    #: Price at computation time (v2 files); None for v1 files.
    price: float | None = None
    #: True when the computation had a price for this ticker.
    prices_available: bool = False
    #: Methodologies that abstained by design (financial company -> "N/A").
    na_count: int = 0

    @property
    def is_data_hole(self) -> bool:
        """True when every methodology said INSUFFICIENT_DATA."""
        return bool(self.verdicts) and self.insufficient_count == len(self.verdicts)

    @property
    def is_not_applicable(self) -> bool:
        """True when every methodology abstained by design (all "N/A")."""
        return bool(self.verdicts) and self.na_count == len(self.verdicts)

    @property
    def is_excluded(self) -> bool:
        """True when a ranking must skip the company (no real verdict at all)."""
        return self.is_data_hole or self.is_not_applicable


@dataclass
class ConsensusReport:
    """A loaded consensus file (v1 or v2)."""

    date: str
    universe: str
    companies: list[CompanyConsensus]
    version: int = 1
    prices_available: bool = False
    prices_snapshot: dict[str, float] = field(default_factory=dict)


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
        max_age_days: int | None = STALE_AFTER_DAYS,
    ) -> None:
        if directory is None:
            # Pinned demo fixtures never expire; production files do.
            from backend.services.demo_mode import is_demo

            self._dir = default_consensus_dir()
            self._max_age_days = None if is_demo() else max_age_days
        else:
            self._dir = Path(directory)
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
        if self._max_age_days is not None and age > self._max_age_days:
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

    def load_file(self, path: Path | str) -> ConsensusReport | None:
        """Load a specific consensus JSON (no staleness check).

        Used by the UI for pinned demo fixtures whose filename does not follow
        the ``consensus_<date>.json`` convention.
        """
        report = self._read(Path(path))
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
            price = row.get("price")
            companies.append(
                CompanyConsensus(
                    ticker=ticker,
                    name=str(row.get("name") or ticker),
                    lynch_category=normalize_lynch_category(
                        str(row.get("lynch_category") or "UNKNOWN")
                    ),
                    verdicts=verdicts,
                    buy_count=int(row.get("buy_count") or 0),
                    avoid_count=int(row.get("avoid_count") or 0),
                    insufficient_count=int(row.get("insufficient_count") or 0),
                    consensus_score=int(row.get("consensus_score") or 0),
                    price=float(price) if price is not None else None,
                    prices_available=bool(row.get("prices_available")),
                    na_count=(
                        int(row["na_count"])
                        if row.get("na_count") is not None
                        else sum(1 for v in verdicts.values() if v == "N/A")
                    ),
                )
            )
        snapshot = {
            str(ticker): float(price)
            for ticker, price in (payload.get("prices_snapshot") or {}).items()
            if price is not None
        }
        return ConsensusReport(
            date=str(payload.get("date") or ""),
            universe=str(payload.get("universe") or ""),
            companies=companies,
            version=int(payload.get("version") or 1),
            prices_available=bool(payload.get("prices_available")),
            prices_snapshot=snapshot,
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
        """Rankable companies (data holes and all-N/A companies excluded)."""
        if self._report is None:
            return []
        return sorted(
            (c for c in self._report.companies if not c.is_excluded),
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
