"""Expense-line service: read XBRL facts and assemble the canonical lines."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.repositories.expense_lines import (
    EXPENSE_LINE_MAP,
    ExpenseLine,
    build_expense_lines,
)
from backend.repositories.expense_overrides import EXPENSE_OVERRIDES

logger = logging.getLogger(__name__)

_ALL_TAGS = tuple(
    dict.fromkeys(tag for tags in EXPENSE_LINE_MAP.values() for tag in tags)
)


@dataclass
class ExpenseReport:
    """One ticker-year's expense lines plus the FX/context used."""

    ticker: str
    name: str
    fiscal_year: int
    currency: str
    fx_rate: float | None
    lines: list[ExpenseLine]
    applicable: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "fiscal_year": self.fiscal_year,
            "currency": self.currency,
            "fx_rate": self.fx_rate,
            "applicable": self.applicable,
            "note": self.note,
            "lines": [line.to_dict() for line in self.lines],
        }


class ExpenseService:
    """Reads ``financial_facts``; never invents a missing disclosure."""

    def __init__(self, repository: Any = None) -> None:
        self._repository = repository

    def _repo(self) -> Any:
        if self._repository is None:
            from backend.app.cli import build_financial_repository

            self._repository = build_financial_repository()
        return self._repository

    def build(
        self, ticker: str, fiscal_year: int | None = None
    ) -> ExpenseReport | None:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return None
        repository = self._repo()
        company_id = getattr(repository, "_get_company_id_by_ticker", lambda _t: None)(
            symbol
        )
        if not company_id:
            return None

        year = fiscal_year or getattr(
            repository, "get_effective_year", lambda _t: None
        )(symbol)
        facts = self._facts(company_id, year) if year else {}
        if not facts and fiscal_year is None:
            year = self._latest_fact_year(company_id)
            facts = self._facts(company_id, year) if year else {}
        if not year:
            # Banks/REITs may have no mapped expense tag at all; still emit an
            # explicit "not applicable" report instead of "no fundamentals".
            try:
                rows = self._repo().get_best_available(symbol, max_years=1)
            except Exception:  # noqa: BLE001
                rows = []
            if rows:
                year = rows[0].fiscal_year
        if not year:
            return None

        core = self._core(company_id, int(year))
        currency = str((core or {}).get("currency") or "USD").upper()
        fx_rate = None
        if core and currency != "USD":
            revenue = core.get("revenue")
            revenue_usd = core.get("revenue_usd")
            if revenue and revenue_usd:
                try:
                    fx_rate = float(revenue_usd) / float(revenue)
                except (TypeError, ValueError, ZeroDivisionError):
                    fx_rate = None

        flags = self._flags(symbol)
        reason = ""
        applicable = True
        if "bank" in flags:
            applicable = False
            reason = "not applicable for banks"
        elif "reit" in flags:
            applicable = False
            reason = "not applicable for REITs"

        lines = build_expense_lines(
            symbol,
            int(year),
            facts,
            currency=currency,
            fx_rate=fx_rate,
            overrides=EXPENSE_OVERRIDES.get(symbol, {}),
            not_applicable_reason=reason or None,
        )
        name = symbol
        getter = getattr(repository, "get_company_name", None)
        if callable(getter):
            try:
                name = getter(symbol) or symbol
            except Exception:  # noqa: BLE001 — the name is cosmetic
                name = symbol
        note = ""
        if currency != "USD":
            note = (
                f"Values converted from {currency} to USD at the fiscal-year "
                "FX rate implied by core revenue."
            )
        return ExpenseReport(
            ticker=symbol,
            name=name,
            fiscal_year=int(year),
            currency=currency,
            fx_rate=fx_rate,
            lines=lines,
            applicable=applicable,
            note=note,
        )

    # ------------------------------------------------------------------
    def _facts(self, company_id: str, fiscal_year: int) -> dict[str, dict]:
        try:
            with self._repo()._get_connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (concept)
                        namespace, concept, value, unit, currency,
                        period_end, filing_date
                    FROM financial_facts
                    WHERE company_id = %s
                      AND fiscal_year = %s
                      AND UPPER(fiscal_period) = 'FY'
                      AND concept = ANY(%s)
                      AND value IS NOT NULL
                    ORDER BY concept, period_end DESC, filing_date DESC
                    """,
                    (company_id, int(fiscal_year), list(_ALL_TAGS)),
                )
                rows = cur.fetchall()
        except Exception:
            logger.debug("expense facts read failed", exc_info=True)
            return {}
        return {
            row["concept"]: dict(row)
            for row in rows
            if hasattr(row, "get") and row.get("concept")
        }

    def _latest_fact_year(self, company_id: str) -> int | None:
        try:
            with self._repo()._get_connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT MAX(fiscal_year) AS year
                    FROM financial_facts
                    WHERE company_id = %s
                      AND UPPER(fiscal_period) = 'FY'
                      AND value IS NOT NULL
                    """,
                    (company_id,),
                )
                row = cur.fetchone()
            return int(row["year"]) if row and row.get("year") else None
        except Exception:  # noqa: BLE001
            return None

    def _core(self, company_id: str, fiscal_year: int) -> dict | None:
        try:
            with self._repo()._get_connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT revenue, revenue_usd, currency
                    FROM core_financials
                    WHERE company_id = %s AND fiscal_year = %s
                    ORDER BY period_end DESC LIMIT 1
                    """,
                    (company_id, int(fiscal_year)),
                )
                row = cur.fetchone()
            return dict(row) if row and hasattr(row, "get") else None
        except Exception:  # noqa: BLE001 — no FX context is not fatal
            return None

    def _flags(self, ticker: str) -> tuple[str, ...]:
        try:
            from backend.methodologies.common.company_type import company_flags

            rows = self._repo().get_best_available(ticker, max_years=1)
            return tuple(company_flags(rows[0] if rows else None))
        except Exception:  # noqa: BLE001
            return ()
