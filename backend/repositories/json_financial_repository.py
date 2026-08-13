"""Structured local-storage fallback for normalized financials.

Used when PostgreSQL is unavailable. Data is persisted as one JSON file per
ticker (``data/normalized/<TICKER>.json``), written atomically so a crash
never leaves a corrupt file behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import NormalizedFinancials


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
                data[str(item.fiscal_year)] = record
            self._write(ticker, data)

    def get_by_year(
        self, ticker: str, fiscal_year: int
    ) -> Optional[NormalizedFinancials]:
        data = self._read(ticker)
        record = data.get(str(fiscal_year))
        return NormalizedFinancials.from_dict(record) if record else None

    def list_years(self, ticker: str) -> list[NormalizedFinancials]:
        data = self._read(ticker)
        records = [NormalizedFinancials.from_dict(r) for r in data.values()]
        records.sort(key=lambda r: r.fiscal_year, reverse=True)
        return records

    def has_data(self, ticker: str) -> bool:
        return self._path(ticker).exists()

    def delete_ticker(self, ticker: str) -> None:
        path = self._path(ticker)
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    def _path(self, ticker: str) -> Path:
        return self._dir / f"{ticker.upper()}.json"

    def _read(self, ticker: str) -> dict:
        path = self._path(ticker)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload.get("years", {}) if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

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
