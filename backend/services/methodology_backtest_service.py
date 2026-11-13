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
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from backend.backtesting.research import (
    quarter_ends,
    rebalance_cost,
    simulate_holding_period,
    target_weights,
)
from backend.methodologies.base import Verdict, is_positive
from backend.methodologies.common.company_type import company_flags
from backend.methodologies.tiers import compute_tiers_from_pairs, compute_year_return

#: Years of history a company needs before it can be evaluated at all.
MIN_ROWS = 3
#: Methodologies the PoC cannot backtest (no historical inputs).
EXCLUDED = frozenset({"greenblatt"})
#: Canonical verdict labels, in display order.
VERDICT_ORDER = (
    "STRONG_BUY",
    "BUY",
    "WEAK_BUY",
    "WATCH",
    "HOLD",
    "AVOID",
    "N/A",
    "INSUFFICIENT_DATA",
)


class _HistoricalPrices:
    """Price context for one evaluation year (never leaks future prices).

    ``beta`` is intentionally ``None`` in the historical simulation: a
    point-in-time beta is not in FDB, and using today's beta would leak
    future information. The DCF then applies its documented 1.0 fallback,
    so the valuation rule is evaluated instead of degrading to ``N/A``.
    """

    def __init__(
        self,
        price: float | None,
        market_cap: float | None,
        beta: float | None = None,
    ) -> None:
        self._price = price
        self._market_cap = market_cap
        self._beta = beta

    def get_current_price(self, _ticker: str) -> float | None:
        return self._price

    def get_market_cap(self, _ticker: str) -> float | None:
        return self._market_cap

    def get_beta(self, _ticker: str) -> float | None:
        return self._beta


@dataclass(frozen=True)
class SignalRecord:
    """One evaluated ticker-year (final tier + raw rule evidence)."""

    ticker: str
    year: int
    verdict: str
    base_verdict: str
    score: float | None
    forward: float
    tier: str | None = None
    failed_rules: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "year": self.year,
            "verdict": self.verdict,
            "base_verdict": self.base_verdict,
            "tier": self.tier,
            "score": self.score,
            "forward": self.forward,
            "failed": list(self.failed_rules),
            "n_failed": len(self.failed_rules),
            "flags": list(self.flags),
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
    turnover: float | None = None
    cost: float | None = None
    rebalances: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "year": self.year,
            "complete": self.complete,
            "buys": self.buys,
            "portfolio_return": self.portfolio_return,
            "benchmark_return": self.benchmark_return,
            "verdicts": dict(self.verdicts),
        }
        if self.turnover is not None:
            payload["turnover"] = self.turnover
        if self.cost is not None:
            payload["cost"] = self.cost
        if self.rebalances:
            payload["rebalances"] = self.rebalances
        if not self.complete:
            payload["label"] = "YTD"
        return payload


@dataclass
class MethodologyBacktest:
    """Aggregated PoC result for one methodology."""

    methodology: str
    years: tuple[int, ...]
    selected_verdict: str = "POSITIVE"
    weighting: str = "tier"
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

    # --- research-grade configuration (v0.34.0) ----------------------------
    research_grade: bool = False
    pit_lag_days: int = 45
    sizing: str = "tier"
    max_weight: float = 0.20
    tc_bps: float = 10.0
    tc_fixed: float = 0.0
    rebalance: str = "annual"
    survivorship_bias: bool = True
    pit_coverage: float | None = None
    universe_by_year: dict[int, dict[str, int]] = field(default_factory=dict)
    snapshot_out: dict[str, dict[str, float]] = field(default_factory=dict)

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
    def tier_counts(self) -> dict[str, int]:
        """Aggregate final counts for the three positive tiers."""
        counts = Counter(record.verdict for record in self.records)
        return {
            label: counts.get(label, 0) for label in ("STRONG_BUY", "BUY", "WEAK_BUY")
        }

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
            "weighting_method": self.weighting,
            "tier_counts": self.tier_counts,
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
            "config": {
                "research_grade": self.research_grade,
                "pit_lag_days": self.pit_lag_days if self.research_grade else None,
                "sizing": self.sizing,
                "max_weight": self.max_weight,
                "tc_bps": self.tc_bps,
                "tc_fixed": self.tc_fixed,
                "rebalance": self.rebalance,
                "survivorship_bias": self.survivorship_bias,
                "pit_coverage": self.pit_coverage,
                "universe_by_year": {
                    str(year): counts
                    for year, counts in sorted(self.universe_by_year.items())
                },
            },
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
        self._run_snapshot: dict[str, dict[str, float]] = {}
        self._snapshot_only = False

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
        weighting: str = "tier",
        universe_name: str = "sp500",
        universe_total: int | None = None,
        today: date | None = None,
        research_grade: bool = False,
        pit_lag_days: int = 45,
        tc_bps: float = 10.0,
        tc_fixed: float = 0.0,
        initial_capital: float = 100_000.0,
        rebalance: str = "annual",
        rebalance_threshold: float = 0.05,
        sizing: str = "tier",
        max_weight: float = 0.20,
        price_snapshot: dict[str, dict[int, float]] | None = None,
        use_historical_universe: bool = True,
        universe_limit: int | None = None,
    ) -> MethodologyBacktest:
        """Backtest one methodology over ``years`` fiscal years.

        ``verdict_filter`` defaults to every positive tier. A named tier
        (``graham:BUY``) selects exactly that tier. ``weighting="tier"`` uses
        the 60/30/10 tier weights; ``"equal"`` is the legacy behaviour. A year
        whose forward window is not complete yet is marked YTD and excluded
        from every CAGR/Sharpe.
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
        selected = verdict_filter.upper() if verdict_filter else "POSITIVE"
        if selected != "POSITIVE" and selected not in {
            verdict.value for verdict in Verdict
        }:
            raise ValueError(f"unknown verdict filter: {selected}")
        weighting = str(weighting).lower()
        if weighting not in ("tier", "equal"):
            raise ValueError(f"unknown weighting: {weighting}")

        research_grade = bool(research_grade)
        rebalance = str(rebalance).lower()
        if rebalance not in ("annual", "quarterly", "threshold"):
            raise ValueError(f"unknown rebalance policy: {rebalance}")
        sizing = str(sizing).lower()
        if sizing not in ("tier", "equal"):
            raise ValueError(f"unknown sizing: {sizing}")
        if not 0 < float(max_weight) <= 1:
            raise ValueError("max_weight must be in (0, 1]")

        reference = today or datetime.now(UTC).date()
        if research_grade:
            return self._run_research(
                method=method,
                name=name,
                tickers=tickers,
                years=years,
                selected=selected,
                weighting=weighting,
                universe_name=universe_name,
                universe_total=universe_total,
                reference=reference,
                pit_lag_days=pit_lag_days,
                tc_bps=tc_bps,
                tc_fixed=tc_fixed,
                initial_capital=initial_capital,
                rebalance=rebalance,
                rebalance_threshold=rebalance_threshold,
                sizing=sizing,
                max_weight=max_weight,
                price_snapshot=price_snapshot,
                use_historical_universe=use_historical_universe,
                universe_limit=universe_limit,
            )

        result = MethodologyBacktest(
            methodology=name,
            years=(),
            selected_verdict=selected,
            weighting=weighting,
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

        raw_by_year: dict[int, list[SignalRecord]] = {}
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
                forward = prices[year + 1] / prices[year] - 1.0
                verdict, failed, score, flags = self._evaluate(
                    method, ticker, rows, prices[year], history
                )
                raw_by_year.setdefault(year, []).append(
                    SignalRecord(
                        ticker=ticker,
                        year=year,
                        verdict=verdict,
                        base_verdict=verdict,
                        score=score,
                        forward=forward,
                        failed_rules=failed,
                        flags=flags,
                    )
                )
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
        signals: Counter = Counter()
        for year in sorted(raw_by_year):
            raw = raw_by_year[year]
            pairs = {
                record.ticker: (Verdict(record.base_verdict), record.score)
                for record in raw
            }
            tier_map = compute_tiers_from_pairs(pairs)
            final_records = []
            for record in raw:
                if record.ticker in tier_map:
                    verdict, tier = tier_map[record.ticker]
                    final_records.append(
                        replace(record, verdict=verdict.value, tier=tier)
                    )
                else:
                    final_records.append(replace(record, tier=None))
            result.records.extend(final_records)
            for record in final_records:
                signals[record.verdict] += 1
            selected_records = [
                record
                for record in final_records
                if self._is_selected(record.verdict, selected)
            ]
            returns = {record.ticker: record.forward for record in final_records}
            verdicts_by_ticker = {
                record.ticker: Verdict(record.verdict) for record in final_records
            }
            if selected == "POSITIVE":
                portfolio_return = compute_year_return(
                    returns, verdicts_by_ticker, weighting
                )
            elif selected_records:
                portfolio_return = statistics.fmean(
                    record.forward for record in selected_records
                )
            else:
                portfolio_return = 0.0
            verdicts = {
                label: int(
                    sum(1 for record in final_records if record.verdict == label)
                )
                for label in VERDICT_ORDER
            }
            year_rows.append(
                YearResult(
                    year=year,
                    buys=len(selected_records),
                    portfolio_return=portfolio_return,
                    benchmark_return=(
                        statistics.fmean(record.forward for record in final_records)
                        if final_records
                        else None
                    ),
                    verdicts=verdicts,
                    complete=self._is_complete(year, reference),
                )
            )
        result.years = tuple(sorted(raw_by_year))
        result.signals = dict(signals)
        result.per_year = year_rows
        result.spy_returns = self._spy_series(sorted(raw_by_year))
        result.notes = self._notes(result, evaluated)
        return result

    def run_all(self, tickers: list[str], years: int = 10) -> list[MethodologyBacktest]:
        return [
            self.run(tickers, name, years=years)
            for name in self.available_methodologies()
        ]

    # -- research-grade path (v0.34.0) --------------------------------------
    def _run_research(
        self,
        *,
        method: Any,
        name: str,
        tickers: list[str],
        years: int,
        selected: str,
        weighting: str,
        universe_name: str,
        universe_total: int | None,
        reference: date,
        pit_lag_days: int,
        tc_bps: float,
        tc_fixed: float,
        initial_capital: float,
        rebalance: str,
        rebalance_threshold: float,
        sizing: str,
        max_weight: float,
        price_snapshot: dict[str, dict[str, float]] | None,
        use_historical_universe: bool,
        universe_limit: int | None,
    ) -> MethodologyBacktest:
        """Point-in-time backtest over the historical S&P 500 universe.

        Every signal year ``Y`` is evaluated at ``Y-12-31 + pit_lag_days``:
        fundamentals are read with ``filing_date <= as_of`` and prices at the
        same date, so the return window starts only after the facts were
        public. The universe is the membership at that same as-of date. A
        delisted constituent without fundamentals or prices is skipped and
        reported as survivorship bias, never silently replaced.
        """
        repo = self._repo()
        self._snapshot_only = price_snapshot is not None
        self._run_snapshot = {
            ticker.upper(): {str(key): float(value) for key, value in series.items()}
            for ticker, series in (price_snapshot or {}).items()
        }

        if not all(
            hasattr(repo, attr) for attr in ("list_years_pit", "get_sp500_universe")
        ):
            raise ValueError(
                "research-grade backtests require Financial-DataBase 0.4.0+ "
                "(point-in-time history and sp500_constituents)"
            )
        custom = [ticker.upper() for ticker in tickers]
        lag = max(0, int(pit_lag_days))
        window = max(1, int(years))
        # Last fiscal year whose forward window has already closed. The
        # common boundary is Dec-31 + lag; a year that still has not closed is
        # not measurable and is not reported as YTD (there is no price yet).
        end_year = reference.year
        while date(end_year + 1, 12, 31) + timedelta(days=lag) > reference:
            end_year -= 1
        year_list = list(range(end_year - window + 1, end_year + 1))

        result = MethodologyBacktest(
            methodology=name,
            years=(),
            selected_verdict=selected,
            weighting=weighting,
            universe_name=universe_name,
            universe_total=universe_total,
            sample_size=len(custom),
            rules=[
                {"id": rule.id, "name": rule.name}
                for rule in getattr(method, "rules", list)()
            ],
            research_grade=True,
            pit_lag_days=lag,
            sizing=sizing,
            max_weight=float(max_weight),
            tc_bps=float(tc_bps),
            tc_fixed=float(tc_fixed),
            rebalance=rebalance,
        )

        can_use_history = (
            use_historical_universe
            and hasattr(repo, "historical_universe_available")
            and hasattr(repo, "get_sp500_universe")
        )
        if can_use_history and repo.historical_universe_available():
            result.notes.append(
                "Historical S&P 500 membership loaded from FDB "
                "sp500_constituents (fja05680)."
            )
        elif use_historical_universe and not custom:
            result.notes.append(
                "Historical universe unavailable; falling back to the current "
                "universe (survivorship bias is larger)."
            )
            can_use_history = False

        all_members: set[str] = set()
        member_years = 0
        evaluated_years = 0
        previous_weights: dict[str, float] = {}
        raw_by_year: dict[int, list[SignalRecord]] = {}
        year_rows: list[YearResult] = []

        for year in year_list:
            as_of = date(year, 12, 31) + timedelta(days=lag)
            next_as_of = date(year + 1, 12, 31) + timedelta(days=lag)
            if next_as_of > reference:
                # The forward window has not ended: no return is measurable,
                # so the year is not a signal year in research mode.
                continue

            if custom:
                members = custom
            elif can_use_history:
                members = repo.get_sp500_universe(as_of)
            else:
                members = custom
            if universe_limit and 0 < int(universe_limit) < len(members):
                step = len(members) / int(universe_limit)
                members = [
                    members[int(index * step)] for index in range(int(universe_limit))
                ]
            if not members:
                continue
            all_members.update(members)
            member_years += len(members)

            raw: list[SignalRecord] = []
            for ticker in members:
                history = repo.list_years_pit(ticker, as_of, max_years=window + 2)
                rows = [row for row in history if row.fiscal_year <= year]
                if len(rows) < MIN_ROWS:
                    continue
                price = self._pit_price(ticker, as_of)
                next_price = (
                    None
                    if next_as_of > reference
                    else self._pit_price(ticker, next_as_of)
                )
                if price is None or next_price is None:
                    continue
                forward = next_price / price - 1.0
                verdict, failed, score, flags = self._evaluate(
                    method,
                    ticker,
                    rows,
                    price,
                    {row.fiscal_year: row for row in rows},
                )
                raw.append(
                    SignalRecord(
                        ticker=ticker,
                        year=year,
                        verdict=verdict,
                        base_verdict=verdict,
                        score=score,
                        forward=forward,
                        failed_rules=failed,
                        flags=flags,
                    )
                )

            if not raw:
                continue
            evaluated_years += len(raw)
            raw_by_year[year] = raw
            result.universe_by_year[year] = {
                "members": len(members),
                "evaluated": len(raw),
            }

            pairs = {
                record.ticker: (Verdict(record.base_verdict), record.score)
                for record in raw
            }
            tier_map = compute_tiers_from_pairs(pairs)
            final_records = []
            for record in raw:
                if record.ticker in tier_map:
                    verdict, tier = tier_map[record.ticker]
                    final_records.append(
                        replace(record, verdict=verdict.value, tier=tier)
                    )
                else:
                    final_records.append(replace(record, tier=None))
            result.records.extend(final_records)

            verdicts = {record.ticker: record.verdict for record in final_records}
            if selected == "POSITIVE":
                eligible = {
                    ticker: verdict
                    for ticker, verdict in verdicts.items()
                    if is_positive(verdict)
                }
            else:
                eligible = {
                    ticker: verdict
                    for ticker, verdict in verdicts.items()
                    if verdict == selected
                }
            weights = target_weights(
                eligible,
                sizing="equal" if selected != "POSITIVE" else sizing,
                max_weight=float(max_weight),
            )
            positive = {
                record.ticker: record.forward
                for record in final_records
                if record.ticker in eligible
            }
            selected_count = len(positive)

            start_cost = rebalance_cost(
                previous_weights,
                weights,
                tc_bps=tc_bps,
                tc_fixed=tc_fixed,
                capital=initial_capital,
            )
            intra = (
                simulate_holding_period(
                    weights,
                    self._pit_price,
                    [as_of] + quarter_ends(as_of, next_as_of),
                    rebalance=rebalance,
                    threshold=rebalance_threshold,
                    tc_bps=tc_bps,
                    tc_fixed=tc_fixed,
                    capital=initial_capital,
                )
                if weights and rebalance != "annual"
                else None
            )

            if intra is not None:
                gross = intra.gross_return
                net = (1.0 + intra.net_return) * (1.0 - start_cost.total) - 1.0
                cost = start_cost.total + intra.cost
                turnover = start_cost.turnover + intra.turnover
                rebalances = intra.rebalances
            else:
                gross = sum(
                    weight * positive.get(ticker, 0.0)
                    for ticker, weight in weights.items()
                )
                net = (1.0 + gross) * (1.0 - start_cost.total) - 1.0
                cost = start_cost.total
                turnover = start_cost.turnover
                rebalances = 0
            previous_weights = weights

            year_rows.append(
                YearResult(
                    year=year,
                    buys=selected_count,
                    portfolio_return=net,
                    benchmark_return=(
                        statistics.fmean(record.forward for record in final_records)
                        if final_records
                        else None
                    ),
                    verdicts={
                        label: int(
                            sum(
                                1 for record in final_records if record.verdict == label
                            )
                        )
                        for label in VERDICT_ORDER
                    },
                    complete=date(year + 1, 12, 31) + timedelta(days=lag) <= reference,
                    turnover=turnover,
                    cost=cost,
                    rebalances=rebalances,
                )
            )

        result.years = tuple(sorted(raw_by_year))
        result.signals = dict(Counter(record.verdict for record in result.records))
        result.per_year = year_rows
        result.spy_returns = self._spy_series(sorted(raw_by_year))
        result.sample_size = len(all_members) if all_members else len(custom)
        if universe_total is None:
            result.universe_total = result.sample_size
        result.pit_coverage = evaluated_years / member_years if member_years else None
        result.survivorship_bias = True
        result.snapshot_out = {
            ticker: dict(sorted(series.items()))
            for ticker, series in self._run_snapshot.items()
        }
        result.notes.extend(
            [
                (
                    f"PIT: filing_date <= fiscal_year_end+{lag}d for each "
                    "fiscal year; prices at the same as-of date."
                ),
                (
                    f"Universe: historical S&P 500 membership per year "
                    f"({member_years} member-years, {len(all_members)} distinct "
                    f"tickers; {evaluated_years} evaluable, "
                    f"{result.pit_coverage:.0%} coverage)."
                    if result.pit_coverage is not None
                    else "Universe: custom ticker list."
                ),
                (
                    f"Costs: {tc_bps:g} bps turnover"
                    + (f" + ${tc_fixed:g}/trade" if tc_fixed else "")
                    + f"; sizing {sizing} (cap {max_weight:.0%}); "
                    f"rebalance {rebalance}."
                ),
                (
                    "Survivorship bias: NOT corrected. Yahoo no longer serves "
                    "delisted symbols, so removed constituents without a live "
                    "price are skipped."
                ),
            ]
        )
        if any(not item.complete for item in result.per_year):
            result.notes.append(
                "YTD year(s) are shown for context but excluded from every CAGR/Sharpe."
            )
        return result

    def _pit_price(self, ticker: str, when: date) -> float | None:
        """Price at ``when``, memoised; snapshot-only mode never hits Yahoo."""
        key = when.isoformat()
        series = self._run_snapshot.setdefault(ticker.upper(), {})
        if key in series:
            return float(series[key])
        if self._snapshot_only:
            return None
        try:
            price = self._price_service().get_price_on_date(ticker, when)
        except Exception:  # noqa: BLE001 — one missing price is a gap
            price = None
        if price is not None:
            series[key] = float(price)
            return float(price)
        return None

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
                "Portfolio = positive signals weighted 60/30/10 by "
                "STRONG_BUY/BUY/WEAK_BUY (re-scaled when a tier is empty); "
                "cash (0%) when a year has no signal."
            ),
            (
                "Tiers are demote-only: only a rule's BUY can be tiered or "
                "demoted; WATCH/HOLD/AVOID are never promoted."
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

    @staticmethod
    def _is_selected(verdict: str, selected: str) -> bool:
        if selected == "POSITIVE":
            return is_positive(verdict)
        if selected == "BUY":
            return verdict == "BUY"
        return verdict == selected

    def _evaluate(
        self,
        method: Any,
        ticker: str,
        rows: list[Any],
        price: float | None,
        history: dict[int, Any],
    ) -> tuple[str, tuple[str, ...], float | None, tuple[str, ...]]:
        latest = rows[-1] if rows else None
        shares = getattr(latest, "shares_outstanding", None) if latest else None
        factor = getattr(latest, "split_adjustment_factor", 1.0) if latest else 1.0
        market_cap = price * shares * factor if price is not None and shares else None
        flags = tuple(sorted(company_flags(latest)))
        try:
            result = method.evaluate(
                ticker, list(reversed(rows)), _HistoricalPrices(price, market_cap)
            )
        except Exception:  # noqa: BLE001 — a methodology failure is INSUFFICIENT
            return Verdict.INSUFFICIENT_DATA.value, (), None, flags
        verdict = getattr(result.verdict, "value", str(result.verdict))
        failed = tuple(getattr(result, "failed_rules", ()) or ())
        score = getattr(result, "score", None)
        return verdict, failed, score, flags
