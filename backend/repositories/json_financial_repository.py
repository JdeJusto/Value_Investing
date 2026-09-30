"""Structured local-storage fallback for normalized financials.

Used when PostgreSQL is unavailable. Data is persisted as one JSON file per
ticker (``data/normalized/<TICKER>.json``), written atomically so a crash
never leaves a corrupt file behind. Multiple sources per year are stored
under ``years[<year>][<source>]``.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.source_selection import best_per_year, choose_history


class JsonFinancialRepository(FinancialRepository):
    """File-based implementation of :class:`FinancialRepository`."""

    def __init__(self, directory: str | Path):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def upsert(self, financials: NormalizedFinancials) -> None:
        self.upsert_many([financials])

    def upsert_many(self, financials: list[NormalizedFinancials]) -> None:
        if not financials:
            return
        by_ticker: dict[str, list[NormalizedFinancials]] = {}
        for item in financials:
            by_ticker.setdefault(item.ticker.upper(), []).append(item)
        for ticker, items in by_ticker.items():
            data = self._read(ticker)
            for item in items:
                record = item.to_dict()
                record["ticker"] = ticker
                data.setdefault(str(item.fiscal_year), {})[self._source_key(item)] = (
                    record
                )
            self._write(ticker, data)

    def get_by_year(self, ticker: str, fiscal_year: int) -> NormalizedFinancials | None:
        data = self._read(ticker)
        year_records = data.get(str(fiscal_year), {})
        records = [
            NormalizedFinancials.from_dict(record) for record in year_records.values()
        ]
        if not records:
            return None
        return best_per_year(records)[0]

    def list_years(self, ticker: str) -> list[NormalizedFinancials]:
        """Best available record per year, most recent first."""
        rows = self.list_all(ticker)
        return best_per_year(rows) if rows else []

    def list_all(self, ticker: str) -> list[NormalizedFinancials]:
        """Every stored record across sources, year desc."""
        data = self._read(ticker)
        records = [
            NormalizedFinancials.from_dict(record)
            for year in data.values()
            for record in year.values()
        ]
        records.sort(
            key=lambda r: (r.fiscal_year, self._record_rank(r)),
            reverse=True,
        )
        return records

    def get_best_available(self, ticker: str) -> list[NormalizedFinancials]:
        """Select the best consistent history (see choose_history)."""
        rows = self.list_all(ticker)
        return choose_history(rows) if rows else []

    def has_data(self, ticker: str) -> bool:
        return self._path(ticker).exists()

    def delete_ticker(self, ticker: str) -> None:
        path = self._path(ticker)
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    @staticmethod
    def _source_key(financials: NormalizedFinancials) -> str:
        return (
            financials.source.value
            if hasattr(financials.source, "value")
            else str(financials.source)
        )

    # FinancialRepository interface extensions for historical data
    def get_shares_outstanding(self, ticker: str, fiscal_year: int) -> float | None:
        """Get shares outstanding from normalized financials for the given year."""
        record = self.get_by_year(ticker, fiscal_year)
        if record and record.shares_outstanding is not None:
            return float(record.shares_outstanding)
        return None

    @staticmethod
    def _record_rank(record: NormalizedFinancials) -> tuple:
        return (
            record.data_source_priority or 0,
            record.data_quality_score if record.data_quality_score is not None else -1,
        )

    def _path(self, ticker: str) -> Path:
        return self._dir / f"{ticker.upper()}.json"

    def _read(self, ticker: str) -> dict:
        """years[<year>][<source>] -> record dict (legacy single-source migrated)."""
        path = self._path(ticker)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            years = payload.get("years", {}) if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

        normalized: dict[str, dict] = {}
        for year, value in years.items():
            if not isinstance(value, dict):
                continue
            if "ticker" in value:
                # Legacy format: years[year] was a single record dict.
                normalized[year] = {
                    self._source_key(NormalizedFinancials.from_dict(value)): value
                }
            else:
                normalized[year] = value
        return normalized

    def _write(self, ticker: str, years: dict) -> None:
        path = self._path(ticker)
        payload = {"ticker": ticker.upper(), "years": years}
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, default=str)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
