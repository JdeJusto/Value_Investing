"""Offline demo mode: preloaded fixtures, no PostgreSQL/SEC/Yahoo.

Enabled with ``VI_DEMO=1`` (the ``--demo`` flag sets it). Everything that
touches an external service is swapped in the composition layer — the
factories in ``backend/app/cli.py``, ``price_service.get_price_service`` and
the Greenblatt rankings directory — so no other module branches on demo
mode.

The fixtures live in ``data/demo/`` (see ``scripts/build_demo_data.py``) and
are pinned snapshots, not live data.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

DEMO_ROOT = Path("data/demo")
DEMO_FUNDAMENTALS = DEMO_ROOT / "fundamentals"
DEMO_PRICES = DEMO_ROOT / "prices.json"
DEMO_RANKINGS = DEMO_ROOT / "rankings"
DEMO_PORTFOLIO = DEMO_ROOT / "portfolio.json"
DEMO_REPORTS = DEMO_ROOT / "reports"

BANNER = "Demo mode — data is preloaded; no external services are used."


def is_demo() -> bool:
    """True when the process runs against the offline demo bundle."""
    return os.environ.get("VI_DEMO") == "1"


def enable_demo() -> None:
    os.environ["VI_DEMO"] = "1"


def load_demo_prices() -> dict[str, float]:
    try:
        data = json.loads(DEMO_PRICES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {ticker.upper(): float(value) for ticker, value in data.items()}


class DemoPriceService:
    """Price source backed by the demo snapshot: never touches the network.

    Duck-typed against :class:`PriceService` (same method names) so it can be
    injected anywhere a price service is expected. Historical lookups return
    the pinned demo price for every date (fixture data, documented as such).
    """

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self._prices = prices if prices is not None else load_demo_prices()
        self._shares: dict[str, float] = {}

    # ------------------------------------------------------------------
    def _shares_outstanding(self, ticker: str) -> float | None:
        key = ticker.upper()
        if key not in self._shares:
            from backend.repositories.json_financial_repository import (
                JsonFinancialRepository,
            )

            rows = JsonFinancialRepository(DEMO_FUNDAMENTALS).get_best_available(key)
            self._shares[key] = (
                float(rows[0].shares_outstanding)
                if rows and rows[0].shares_outstanding
                else 0.0
            )
        return self._shares[key] or None

    def _market_cap(self, ticker: str) -> float | None:
        price = self.get_current_price(ticker)
        shares = self._shares_outstanding(ticker)
        if price is None or shares is None:
            return None
        return price * shares

    # ------------------------------------------------------------------
    # prices
    # ------------------------------------------------------------------
    def get_current_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker.upper())

    def get_current_prices(
        self,
        tickers: list[str],
        batch_size: int = 25,
        delay: float = 0.5,
        workers: int = 1,
    ) -> dict[str, float | None]:
        return {ticker.upper(): self._prices.get(ticker.upper()) for ticker in tickers}

    def get_historical_prices(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[tuple[date, float]]:
        price = self.get_current_price(ticker)
        if price is None:
            return []
        end = end_date or datetime.now(UTC).date()
        start = start_date or (end - timedelta(days=365))
        return [(start, price), (end, price)]

    def get_price_on_date(self, ticker: str, target_date: date) -> float | None:
        return self.get_current_price(ticker)

    def get_price_at_fiscal_year_end(
        self,
        ticker: str,
        fiscal_year: int,
        fiscal_year_end_date: date | None = None,
    ) -> float | None:
        return self.get_current_price(ticker)

    def get_split_adjustment(self, ticker: str, target_date: date) -> float:
        return 1.0

    # ------------------------------------------------------------------
    # market data
    # ------------------------------------------------------------------
    def get_shares_outstanding(self, ticker: str) -> int | None:
        shares = self._shares_outstanding(ticker)
        return int(shares) if shares is not None else None

    def get_market_cap(self, ticker: str) -> float | None:
        return self._market_cap(ticker)

    def get_enterprise_value(self, ticker: str) -> float | None:
        from backend.repositories.json_financial_repository import (
            JsonFinancialRepository,
        )

        market_cap = self._market_cap(ticker)
        rows = JsonFinancialRepository(DEMO_FUNDAMENTALS).get_best_available(
            ticker.upper()
        )
        if market_cap is None or not rows:
            return None
        latest = rows[0]
        debt = latest.total_debt or 0.0
        cash = latest.cash_and_equivalents or 0.0
        return market_cap + debt - cash

    def get_beta(self, ticker: str) -> float | None:
        return None

    def get_market_snapshots(
        self,
        tickers: list[str],
        batch_size: int = 25,
        delay: float = 0.2,
        workers: int = 1,
        preflight: bool = True,
    ) -> dict[str, dict | None]:
        snapshots: dict[str, dict | None] = {}
        for ticker in tickers:
            key = ticker.upper()
            price = self._prices.get(key)
            snapshots[key] = (
                None
                if price is None
                else {
                    "regularMarketPrice": price,
                    "marketCap": self._market_cap(key),
                    "sharesOutstanding": self._shares_outstanding(key),
                }
            )
        return snapshots


def demo_rankings_dir() -> Path:
    """Where the Greenblatt methodology reads rankings from in demo mode."""
    return DEMO_RANKINGS


def demo_context() -> dict[str, Any]:
    """Small summary used by the UI banner and tests."""
    return {
        "enabled": is_demo(),
        "fundamentals": str(DEMO_FUNDAMENTALS),
        "prices": str(DEMO_PRICES),
        "tickers": sorted(load_demo_prices()),
    }
