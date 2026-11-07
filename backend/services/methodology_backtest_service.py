"""Historical backtest of the book methodologies (PoC).

Design: ``docs/backtesting_design.md``. For every fiscal-year end in the
window, each methodology is re-evaluated with **only the rows known at that
time** (no look-ahead in the fundamentals); the selected verdict is held one
year and its forward return is measured from that fiscal-year-end price to the
next one.

The PoC intentionally keeps the model simple:

- equal-weighted selected sets, yearly rebalance, cash (0%) when a year has
  no selected signal;
- **opportunity set** = equal-weighted return of every ticker that could be
  priced in the same year (the comparison that isolates the screen);
- **SPY** = secondary market benchmark, price at the fiscal-year end;
- Sharpe = mean/std of the yearly returns, **no risk-free rate**;
- a year whose forward window is not complete yet is marked YTD and excluded
  from every CAGR/Sharpe;
- Greenblatt is excluded: its verdict comes from the current ranking file,
  which did not exist historically, so backtesting it would be pure
  look-ahead.

Prices are fetched on demand through :class:`PriceService` (Yahoo) and never
persisted.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from backend.methodologies.base import Verdict

#: Years of history a company needs before it can be evaluated at all.
MIN_ROWS = 3
#: Methodologies the PoC cannot backtest (no historical inputs).
EXCLUDED = frozenset({"greenblatt"})
#: Canonical verdict labels, in display order.
VERDICT_ORDER = ("BUY", "WATCH", "HOLD", "AVOID", "N/A", "INSUFFICIENT_DATA")


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
class SignalRecord:
    """One evaluated ticker-year (used for the closest-to-selected summary)."""

    ticker: str
    year: int
    verdict: str
    failed_rules: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "year": self.year,
            "verdict": self.verdict,
            "failed": list(self.failed_rules),
            "n_failed": len(self.failed_rules),
        }


@dataclass(frozen=True)
class YearResult:
    """One signal year: selected count, returns, verdicts and completeness."""

    year: int
    buys: int
    portfolio_return: float | None
    benchmark_return: float | None
    verdicts: dict[str, int] = field(default_factory=dict)
    complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "year": self.year,
            "complete": self.complete,
            "buys": self.buys,
            "portfolio_return": self.portfolio_return,
            "benchmark_return": self.benchmark_return,
            "verdicts": dict(self.verdicts),
        }
        if not self.complete:
            payload["label"] = "YTD"
        return payload


@dataclass
class MethodologyBacktest:
    """Aggregated PoC result for one methodology."""

    methodology: str
    years: tuple[int, ...]
    selected_verdict: str = "BUY"
    universe_name: str = "sp500"
    universe_total: int | None = None
    sample_size: int = 0
    signals: dict[str, int] = field(default_factory=dict)
    per_year: list[YearResult] = field(default_factory=list)
    records: list[SignalRecord] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    spy_returns: dict[int, float] = field(default_factory=dict)
    rules: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # --- derived metrics ---------------------------------------------------
    @property
    def complete_years(self) -> tuple[int, ...]:
        return tuple(item.year for item in self.per_year if item.complete)

    @property
    def evaluated(self) -> int:
        return len({record.ticker for record in self.records})

    @property
    def buy_signals(self) -> int:
        """Selected signals across every year (including a YTD year)."""
        return sum(item.buys for item in self.per_year)

    @property
    def invested_years(self) -> int:
        return sum(1 for item in self.per_year if item.complete and item.buys > 0)

    def _complete_returns(self, attribute: str) -> list[float]:
        return [
            value
            for item in self.per_year
            if item.complete and (value := getattr(item, attribute)) is not None
        ]

    @staticmethod
    def _cagr(returns: list[float]) -> float | None:
        if not returns:
            return None
        growth = 1.0
        for value in returns:
            growth *= 1.0 + value
        if growth <= 0:
            return -1.0
        return growth ** (1.0 / len(returns)) - 1.0

    @staticmethod
    def _sharpe(returns: list[float]) -> float | None:
        if len(returns) < 2:
            return None
        deviation = statistics.pstdev(returns)
        if deviation == 0:
            return None
        return statistics.fmean(returns) / deviation

    @property
    def annualized_return(self) -> float | None:
        """Compound every **complete** year, cash years included at 0%."""
        return self._cagr(self._complete_returns("portfolio_return"))

    @property
    def mean_year_return(self) -> float | None:
        returns = self._complete_returns("portfolio_return")
        return statistics.fmean(returns) if returns else None

    @property
    def hit_rate(self) -> float | None:
        """Share of **invested complete** years with a positive return."""
        returns = [
            item.portfolio_return
            for item in self.per_year
            if item.complete and item.buys > 0 and item.portfolio_return is not None
        ]
        if not returns:
            return None
        return sum(1 for value in returns if value > 0) / len(returns)

    @property
    def sharpe(self) -> float | None:
        return self._sharpe(self._complete_returns("portfolio_return"))

    @property
    def benchmark_annualized(self) -> float | None:
        """Backwards-compatible name: the opportunity set CAGR."""
        return self.opportunity_set_annualized

    @property
    def opportunity_set_annualized(self) -> float | None:
        return self._cagr(self._complete_returns("benchmark_return"))

    @property
    def opportunity_set_sharpe(self) -> float | None:
        return self._sharpe(self._complete_returns("benchmark_return"))

    @property
    def _complete_spy_returns(self) -> list[float]:
        returns: list[float] = []
        for year in self.complete_years:
            if year in self.spy_returns and year + 1 in self.spy_returns:
                returns.append(
                    self.spy_returns[year + 1] / self.spy_returns[year] - 1.0
                )
        return returns

    @property
    def spy_annualized(self) -> float | None:
        return self._cagr(self._complete_spy_returns)

    @property
    def spy_sharpe(self) -> float | None:
        return self._sharpe(self._complete_spy_returns)

    @property
    def alpha_vs_opportunity_set(self) -> float | None:
        if self.annualized_return is None or self.opportunity_set_annualized is None:
            return None
        return self.annualized_return - self.opportunity_set_annualized

    @property
    def alpha_vs_spy(self) -> float | None:
        if self.annualized_return is None or self.spy_annualized is None:
            return None
        return self.annualized_return - self.spy_annualized

    @property
    def no_buy_reason(self) -> dict[str, Any]:
        """Closest ticker-years to the selected verdict (fewest failed rules).

        Only scored verdicts participate: an N/A company (bank/REIT) has no
        failed rule to compare and would otherwise look like the closest.
        """
        scored = [
            record
            for record in self.records
            if record.verdict in {"BUY", "WATCH", "HOLD", "AVOID"}
        ]
        ordered = sorted(
            scored,
            key=lambda record: (len(record.failed_rules), record.ticker, record.year),
        )
        return {
            "rules": self.rules,
            "verdict": self.selected_verdict,
            "closest": [record.to_dict() for record in ordered[:3]],
            "counts": {
                "lt3_failed": sum(
                    1 for record in scored if len(record.failed_rules) < 3
                ),
                "lt5_failed": sum(
                    1 for record in scored if len(record.failed_rules) < 5
                ),
            },
        }

    def to_dict(self) -> dict[str, Any]:
        performance = {
            "portfolio_cagr": self.annualized_return,
            "opportunity_set_cagr": self.opportunity_set_annualized,
            "spy_cagr": self.spy_annualized,
            "alpha_vs_opportunity_set": self.alpha_vs_opportunity_set,
            "alpha_vs_spy": self.alpha_vs_spy,
            "portfolio_sharpe": self.sharpe,
            "opportunity_set_sharpe": self.opportunity_set_sharpe,
            "spy_sharpe": self.spy_sharpe,
            "complete_years": list(self.complete_years),
        }
        return {
            "methodology": self.methodology,
            "verdict_filter": self.selected_verdict,
            "universe": {
                "name": self.universe_name,
                "evaluated": self.evaluated,
                "total": self.sample_size,
                "sample_of": self.universe_total,
            },
            "years": [
                {
                    "year": item.year,
                    "complete": item.complete,
                    **({} if item.complete else {"label": "YTD"}),
                }
                for item in self.per_year
            ],
            "verdicts_by_year": {
                str(item.year): dict(item.verdicts) for item in self.per_year
            },
            "signals": dict(self.signals),
            "buy_signals": self.buy_signals,
            "invested_years": self.invested_years,
            "hit_rate": self.hit_rate,
            "annualized_return": self.annualized_return,
            "benchmark_annualized": self.opportunity_set_annualized,
            "sharpe": self.sharpe,
            "performance": performance,
            "no_buy_reason": self.no_buy_reason,
            "skipped_tickers": list(self.skipped),
            "notes": list(self.notes),
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
        *,
        verdict_filter: str | None = None,
        universe_name: str = "sp500",
        universe_total: int | None = None,
        today: date | None = None,
    ) -> MethodologyBacktest:
        """Backtest one methodology over ``years`` fiscal years.

        ``verdict_filter`` selects which verdict is held (default BUY); it also
        powers ``--methodology graham:BUY``. A year whose forward window is not
        complete yet (``today`` before the end of year + 1) is marked YTD and
        excluded from every CAGR/Sharpe.
        """
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
        selected = (verdict_filter or Verdict.BUY.value).upper()
        if selected not in {verdict.value for verdict in Verdict}:
            raise ValueError(f"unknown verdict filter: {selected}")

        reference = today or datetime.now(UTC).date()
        result = MethodologyBacktest(
            methodology=name,
            years=(),
            selected_verdict=selected,
            universe_name=universe_name,
            universe_total=universe_total,
            sample_size=len(tickers),
            rules=[
                {"id": rule.id, "name": rule.name}
                for rule in getattr(method, "rules", list)()
            ],
        )
        if not tickers:
            return result

        per_year: dict[int, dict[str, Any]] = {}
        signals: dict[str, int] = Counter()
        evaluated = 0
        for ticker in tickers:
            history = self._history(ticker, years)
            if not history:
                result.skipped.append({"ticker": ticker, "reason": "no fundamentals"})
                continue
            prices = self._price_series(ticker, history)
            if len(prices) < 2:
                result.skipped.append(
                    {
                        "ticker": ticker,
                        "reason": f"no usable prices ({len(prices)} fiscal years)",
                    }
                )
                continue
            ticker_signals = 0
            for year in sorted(history):
                if year + 1 not in prices or year not in prices:
                    continue
                rows = [row for row in history.values() if row.fiscal_year <= year]
                if len(rows) < MIN_ROWS:
                    continue
                bucket = per_year.setdefault(
                    year,
                    {"selected": [], "market": [], "verdicts": Counter()},
                )
                forward = prices[year + 1] / prices[year] - 1.0
                bucket["market"].append(forward)
                verdict, failed = self._evaluate(
                    method, ticker, rows, prices[year], history
                )
                signals[verdict] += 1
                bucket["verdicts"][verdict] += 1
                result.records.append(
                    SignalRecord(
                        ticker=ticker,
                        year=year,
                        verdict=verdict,
                        failed_rules=failed,
                    )
                )
                if verdict == selected:
                    bucket["selected"].append(forward)
                ticker_signals += 1
                evaluated += 1
            if not ticker_signals:
                available = f"FY{min(history)}..FY{max(history)}" if history else "none"
                result.skipped.append(
                    {
                        "ticker": ticker,
                        "reason": (
                            f"insufficient history for a signal year ({available})"
                        ),
                    }
                )

        year_rows: list[YearResult] = []
        for year in sorted(per_year):
            bucket = per_year[year]
            selected_returns = bucket["selected"]
            verdicts = {
                label: int(bucket["verdicts"].get(label, 0)) for label in VERDICT_ORDER
            }
            year_rows.append(
                YearResult(
                    year=year,
                    buys=len(selected_returns),
                    portfolio_return=(
                        statistics.fmean(selected_returns) if selected_returns else 0.0
                    ),
                    benchmark_return=(
                        statistics.fmean(bucket["market"]) if bucket["market"] else None
                    ),
                    verdicts=verdicts,
                    complete=self._is_complete(year, reference),
                )
            )
        result.years = tuple(sorted(per_year))
        result.signals = dict(signals)
        result.per_year = year_rows
        result.spy_returns = self._spy_series(sorted(per_year))
        result.notes = self._notes(result, evaluated)
        return result

    def run_all(self, tickers: list[str], years: int = 10) -> list[MethodologyBacktest]:
        return [
            self.run(tickers, name, years=years)
            for name in self.available_methodologies()
        ]

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _is_complete(year: int, reference: date) -> bool:
        """A forward window is complete once year + 1 has ended (Dec-31)."""
        return date(year + 1, 12, 31) <= reference

    def _spy_series(self, years: list[int]) -> dict[int, float]:
        """SPY closes at each year end (secondary benchmark; may be empty)."""
        prices: dict[int, float] = {}
        service = self._price_service()
        for year in years:
            try:
                price = service.get_price_at_fiscal_year_end("SPY", year)
            except Exception:  # noqa: BLE001 — a missing SPY is not fatal
                price = None
            if price is not None:
                prices[year] = float(price)
        return prices

    def _notes(self, result: MethodologyBacktest, evaluated: int) -> list[str]:
        notes = [
            (
                "PoC. No dividends, no survivorship correction, no transaction "
                "costs. For research-grade, see docs/backlog.md."
            ),
            (
                "Opportunity set = equal-weighted every priced ticker in the "
                "sample, same fiscal-year window."
            ),
            (
                "Portfolio = selected verdict equal-weighted; cash (0%) when a "
                "year has no signal."
            ),
        ]
        if any(not item.complete for item in result.per_year):
            notes.append(
                "YTD year(s) are shown for context but excluded from every CAGR/Sharpe."
            )
        if result.universe_total and result.sample_size < result.universe_total:
            notes.append(
                f"Sample of {result.sample_size} of {result.universe_total} "
                f"{result.universe_name.upper()} tickers; {evaluated} produced "
                "an evaluable signal."
            )
        return notes

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

    def _evaluate(
        self,
        method: Any,
        ticker: str,
        rows: list[Any],
        price: float | None,
        history: dict[int, Any],
    ) -> tuple[str, tuple[str, ...]]:
        latest = rows[-1] if rows else None
        shares = getattr(latest, "shares_outstanding", None) if latest else None
        factor = getattr(latest, "split_adjustment_factor", 1.0) if latest else 1.0
        market_cap = price * shares * factor if price is not None and shares else None
        try:
            result = method.evaluate(
                ticker, list(reversed(rows)), _HistoricalPrices(price, market_cap)
            )
        except Exception:  # noqa: BLE001 — a methodology failure is INSUFFICIENT
            return Verdict.INSUFFICIENT_DATA.value, ()
        verdict = getattr(result.verdict, "value", str(result.verdict))
        failed = tuple(getattr(result, "failed_rules", ()) or ())
        return verdict, failed
