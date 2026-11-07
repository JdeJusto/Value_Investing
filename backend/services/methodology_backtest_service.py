"""Historical backtest of the book methodologies (PoC).

Design: ``docs/backtesting_design.md``. For every fiscal-year end in the
window, each methodology is re-evaluated with **only the rows known at that
time** (no look-ahead in the fundamentals); a BUY is held one year and its
forward return is measured from that fiscal-year-end price to the next one.

The PoC intentionally keeps the model simple:

- equal-weighted BUY sets, yearly rebalance, cash (0%) when a year has no BUY;
- benchmark = equal-weighted return of every ticker that could be priced;
- Sharpe = mean/std of the yearly returns, **no risk-free rate**;
- Greenblatt is excluded: its verdict comes from the current ranking file,
  which did not exist historically, so backtesting it would be pure
  look-ahead.

Prices are fetched on demand through :class:`PriceService` (Yahoo) and never
persisted.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.methodologies.base import Verdict

#: Years of history a company needs before it can be evaluated at all.
MIN_ROWS = 3
#: Methodologies the PoC cannot backtest (no historical inputs).
EXCLUDED = frozenset({"greenblatt"})


class _HistoricalPrices:
    """Price context for one evaluation year (never leaks future prices)."""

    def __init__(self, price: float | None, market_cap: float | None) -> None:
        self._price = price
        self._market_cap = market_cap

    def get_current_price(self, _ticker: str) -> float | None:
        return self._price

    def get_market_cap(self, _ticker: str) -> float | None:
        return self._market_cap


@dataclass(frozen=True)
class YearResult:
    """One signal year: BUY count, portfolio return and benchmark return."""

    year: int
    buys: int
    portfolio_return: float | None
    benchmark_return: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "buys": self.buys,
            "portfolio_return": self.portfolio_return,
            "benchmark_return": self.benchmark_return,
        }


@dataclass
class MethodologyBacktest:
    """Aggregated PoC result for one methodology."""

    methodology: str
    years: tuple[int, ...]
    signals: dict[str, int] = field(default_factory=dict)
    per_year: list[YearResult] = field(default_factory=list)

    # --- derived metrics ---------------------------------------------------
    @property
    def buy_signals(self) -> int:
        return sum(item.buys for item in self.per_year)

    @property
    def invested_years(self) -> int:
        return sum(1 for item in self.per_year if item.buys > 0)

    @property
    def annualized_return(self) -> float | None:
        """Compound every signal year, cash years included at 0%."""
        returns = [
            item.portfolio_return
            for item in self.per_year
            if item.portfolio_return is not None
        ]
        if not returns:
            return None
        growth = 1.0
        for value in returns:
            growth *= 1.0 + value
        if growth <= 0:
            return -1.0
        return growth ** (1.0 / len(returns)) - 1.0

    @property
    def mean_year_return(self) -> float | None:
        returns = [
            item.portfolio_return
            for item in self.per_year
            if item.portfolio_return is not None
        ]
        return statistics.fmean(returns) if returns else None

    @property
    def hit_rate(self) -> float | None:
        """Share of **invested** years with a positive return."""
        returns = [
            item.portfolio_return
            for item in self.per_year
            if item.buys > 0 and item.portfolio_return is not None
        ]
        if not returns:
            return None
        return sum(1 for value in returns if value > 0) / len(returns)

    @property
    def sharpe(self) -> float | None:
        """Mean/std of the yearly returns; no risk-free rate (PoC)."""
        returns = [
            item.portfolio_return
            for item in self.per_year
            if item.portfolio_return is not None
        ]
        if len(returns) < 2:
            return None
        deviation = statistics.pstdev(returns)
        if deviation == 0:
            return None
        return statistics.fmean(returns) / deviation

    @property
    def benchmark_annualized(self) -> float | None:
        returns = [
            item.benchmark_return
            for item in self.per_year
            if item.benchmark_return is not None
        ]
        if not returns:
            return None
        growth = 1.0
        for value in returns:
            growth *= 1.0 + value
        if growth <= 0:
            return -1.0
        return growth ** (1.0 / len(returns)) - 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "methodology": self.methodology,
            "years": list(self.years),
            "signals": self.signals,
            "buy_signals": self.buy_signals,
            "invested_years": self.invested_years,
            "annualized_return": self.annualized_return,
            "mean_year_return": self.mean_year_return,
            "benchmark_annualized": self.benchmark_annualized,
            "hit_rate": self.hit_rate,
            "sharpe": self.sharpe,
            "per_year": [item.to_dict() for item in self.per_year],
        }


class MethodologyBacktestService:
    """Re-evaluate methodologies year by year and measure forward returns."""

    def __init__(
        self,
        repository: Any = None,
        price_service: Any = None,
        methodology_registry: Any = None,
    ) -> None:
        self._repository = repository
        self._prices = price_service
        self._registry = methodology_registry

    # -- lazy collaborators -------------------------------------------------
    def _repo(self) -> Any:
        if self._repository is None:
            from backend.app.cli import build_financial_repository

            self._repository = build_financial_repository()
        return self._repository

    def _price_service(self) -> Any:
        if self._prices is None:
            from backend.services.price_service import get_price_service

            self._prices = get_price_service()
        return self._prices

    def _methodologies(self) -> Any:
        if self._registry is None:
            from backend.methodologies.registry import discover, registry

            discover()
            self._registry = registry
        return self._registry

    # -- public API ---------------------------------------------------------
    def available_methodologies(self) -> list[str]:
        """Registered methodologies the PoC can backtest, sorted."""
        return sorted(
            name for name in self._methodologies().list() if name not in EXCLUDED
        )

    def run(
        self,
        tickers: list[str],
        methodology: str,
        years: int = 10,
    ) -> MethodologyBacktest:
        """Backtest one methodology over ``years`` fiscal years."""
        name = str(methodology).lower().strip()
        if name in EXCLUDED:
            raise ValueError(
                f"{name} cannot be backtested historically: its ranking file is "
                "point-in-time (current), so any historical verdict would be "
                "look-ahead"
            )
        method = self._methodologies().get(name)
        if method is None:
            raise ValueError(f"unknown methodology: {methodology}")
        result = MethodologyBacktest(methodology=name, years=())
        if not tickers:
            return result

        per_year: dict[int, dict[str, list[float]]] = {}
        signals: dict[str, int] = {}
        seen_years: set[int] = set()
        for ticker in tickers:
            history = self._history(ticker, years)
            if not history:
                continue
            prices = self._price_series(ticker, history)
            for year in sorted(history):
                if year + 1 not in prices or year not in prices:
                    continue
                rows = [row for row in history.values() if row.fiscal_year <= year]
                if len(rows) < MIN_ROWS:
                    continue
                seen_years.add(year)
                result_year = per_year.setdefault(year, {"buys": [], "market": []})
                forward = prices[year + 1] / prices[year] - 1.0
                result_year["market"].append(forward)
                verdict = self._verdict(method, ticker, rows, prices[year], history)
                signals[verdict] = signals.get(verdict, 0) + 1
                if verdict == Verdict.BUY.value:
                    result_year["buys"].append(forward)

        year_rows: list[YearResult] = []
        for year in sorted(per_year):
            bucket = per_year[year]
            buys = bucket["buys"]
            year_rows.append(
                YearResult(
                    year=year,
                    buys=len(buys),
                    portfolio_return=statistics.fmean(buys) if buys else 0.0,
                    benchmark_return=(
                        statistics.fmean(bucket["market"]) if bucket["market"] else None
                    ),
                )
            )
        result.years = tuple(sorted(seen_years))
        result.signals = signals
        result.per_year = year_rows
        return result

    def run_all(self, tickers: list[str], years: int = 10) -> list[MethodologyBacktest]:
        return [
            self.run(tickers, name, years=years)
            for name in self.available_methodologies()
        ]

    # -- helpers ------------------------------------------------------------
    def _history(self, ticker: str, years: int) -> dict[int, Any]:
        """One row per fiscal year, ascending, capped to the requested window."""
        how_many = max(int(years) + 1, MIN_ROWS + 1)
        try:
            rows = self._repo().list_all(ticker, max_years=how_many + 1)
        except TypeError:
            rows = self._repo().list_all(ticker)[-how_many:]
        except Exception:  # noqa: BLE001 — one unreadable ticker is skipped
            return {}
        by_year: dict[int, Any] = {}
        for row in rows or []:
            year = getattr(row, "fiscal_year", None)
            if year is not None and year not in by_year:
                by_year[int(year)] = row
        return dict(sorted(by_year.items()))

    def _price_series(self, ticker: str, history: dict[int, Any]) -> dict[int, float]:
        """Fiscal-year-end closes keyed by fiscal year (tolerates gaps)."""
        prices: dict[int, float] = {}
        service = self._price_service()
        for year in history:
            end = None
            getter = getattr(self._repo(), "get_fiscal_year_end_date", None)
            if getter is not None:
                try:
                    end = getter(ticker, year)
                except Exception:  # noqa: BLE001 — fall back to Dec-31
                    end = None
            try:
                price = service.get_price_at_fiscal_year_end(
                    ticker, year, end if isinstance(end, date) else None
                )
            except Exception:  # noqa: BLE001 — one bad year is a gap
                price = None
            if price is not None:
                prices[year] = float(price)
        return prices

    def _verdict(
        self,
        method: Any,
        ticker: str,
        rows: list[Any],
        price: float | None,
        history: dict[int, Any],
    ) -> str:
        latest = rows[-1] if rows else None
        shares = getattr(latest, "shares_outstanding", None) if latest else None
        factor = getattr(latest, "split_adjustment_factor", 1.0) if latest else 1.0
        market_cap = price * shares * factor if price is not None and shares else None
        try:
            result = method.evaluate(
                ticker, list(reversed(rows)), _HistoricalPrices(price, market_cap)
            )
        except Exception:  # noqa: BLE001 — a methodology failure is INSUFFICIENT
            return Verdict.INSUFFICIENT_DATA.value
        return getattr(result.verdict, "value", str(result.verdict))
