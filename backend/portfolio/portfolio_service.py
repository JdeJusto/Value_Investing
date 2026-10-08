"""Portfolio service: tracks positions and connects them to intelligence.

The analyzer is the analytics-layer entry point (it may refresh prices
and scores); the service itself never touches providers directly.

Concurrency invariant: every read-modify-write cycle (add, exit, remove,
save_prices, view, performance) runs inside an exclusive ``fcntl.flock``
on ``<portfolio>.lock``, so concurrent writers — the API, the CLI and the
Streamlit UI — can never lose an update.
"""

import fcntl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backend.portfolio.allocation import (
    overconcentration,
    risk_concentration,
    sector_exposure,
)
from backend.portfolio.models import Portfolio, Position
from backend.portfolio.performance import portfolio_performance
from backend.portfolio.portfolio_repository import PortfolioRepository
from backend.screener.opportunity_engine import best_opportunity
from backend.screener.ranking_engine import rank_score
from backend.screener.signals import generate_signal

Analyzer = Callable[[str], dict | None]


class PortfolioService:
    def __init__(
        self,
        repository: PortfolioRepository,
        analyzer: Analyzer | None = None,
    ):
        self._repository = repository
        self._analyzer = analyzer

    # ------------------------------------------------------------------
    # write lock
    # ------------------------------------------------------------------
    @contextmanager
    def _locked_portfolio(self) -> Iterator[Portfolio]:
        """Exclusive-lock read → yield → save.

        ``fcntl.flock`` (blocking) serializes the whole critical section
        across threads *and* processes; the lock file lives next to the
        portfolio JSON. Repositories without a ``lock_path`` (in-memory test
        doubles) degrade to a plain load/save — single-process callers only.
        """
        lock_path = self._lock_path()
        if lock_path is None:
            portfolio = self._load()
            yield portfolio
            self._save(portfolio)
            return
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                portfolio = self._load()
                yield portfolio
                self._save(portfolio)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _lock_path(self) -> Path | None:
        lock_path = getattr(self._repository, "lock_path", None)
        return Path(lock_path) if lock_path is not None else None

    # ------------------------------------------------------------------
    # mutations
    # ------------------------------------------------------------------
    def add(
        self,
        ticker: str,
        quantity: float,
        avg_price: float,
        entry_date: datetime | None = None,
        thesis: str = "",
        signal_at_entry: str = "",
    ) -> Position:
        """Open (or average into) a position, saving the thesis."""
        t = ticker.upper().strip()
        position = Position(
            ticker=t,
            quantity=quantity,
            avg_price=avg_price,
            current_price=avg_price,
            entry_date=entry_date or datetime.now(UTC),
            thesis=thesis,
            signal_at_entry=signal_at_entry,
        )
        with self._locked_portfolio() as portfolio:
            portfolio.add(position)
        return position

    def exit(self, ticker: str, price: float) -> Position | None:
        """Close a position at ``price`` and record realized PnL."""
        with self._locked_portfolio() as portfolio:
            closed = portfolio.close(ticker, price)
        return closed

    def remove(self, ticker: str) -> Position | None:
        with self._locked_portfolio() as portfolio:
            removed = portfolio.remove(ticker)
        return removed

    def save_prices(self, prices: dict[str, float]) -> int:
        """Persist refreshed prices (ticker -> price); returns how many.

        The single price-write path: the Streamlit "Save prices" buttons and
        anything else persist through here, so the update always happens
        inside the exclusive lock against the freshest portfolio state.
        Unknown tickers and non-positive prices are ignored (no fabricated
        price is ever stored).
        """
        updated = 0
        with self._locked_portfolio() as portfolio:
            for ticker, raw_price in (prices or {}).items():
                position = portfolio.position(ticker)
                if position is None:
                    continue
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                position.current_price = price
                updated += 1
        return updated

    # ------------------------------------------------------------------
    def view(self) -> list[dict]:
        """Every open position enriched with scores, moat and signal."""
        with self._locked_portfolio() as portfolio:
            self._refresh_prices(portfolio)
            enriched: list[dict] = []
            for position in portfolio.positions:
                if not position.is_open:
                    continue
                info = self._analysis_for(position)
                is_live = info.pop("current_price_source") == "live"
                enriched.append(
                    {
                        "ticker": position.ticker,
                        "quantity": position.quantity,
                        "avg_price": position.avg_price,
                        "current_price": position.current_price,
                        "entry_date": position.entry_date.isoformat(),
                        "thesis": position.thesis,
                        "signal_at_entry": position.signal_at_entry,
                        "unrealized_return": position.unrealized_return,
                        "price_source": "live" if is_live else "stored",
                        **info,
                    }
                )
        return enriched

    def performance(self) -> dict:
        """Performance snapshot plus allocation warnings."""
        with self._locked_portfolio() as portfolio:
            self._refresh_prices(portfolio)
            perf = portfolio_performance(portfolio)
            sectors = self._sector_map(portfolio)
            perf["allocation"] = {
                "overconcentrated": overconcentration(portfolio),
                "sector_exposure": sector_exposure(portfolio, sectors),
                "risk": risk_concentration(portfolio),
            }
        return perf

    # ------------------------------------------------------------------
    def _load(self) -> Portfolio:
        return self._repository.load()

    def _save(self, portfolio: Portfolio) -> None:
        self._repository.save(portfolio)

    def _refresh_prices(self, portfolio: Portfolio) -> None:
        """Update stored prices from the analyzer (best effort)."""
        for position in portfolio.positions:
            if position.is_open:
                self._analysis_for(position)

    def _analysis_for(self, position: Position) -> dict:
        """Refresh price and attach intelligence metadata for a position."""
        if self._analyzer is None:
            return {
                "current_price_source": "stored",
                "buffett_score": None,
                "moat": None,
                "signal": None,
                "opportunity_type": None,
            }
        try:
            result = self._analyzer(position.ticker)
        except Exception:  # noqa: BLE001 — stale prices must not break the view
            result = None
        if not result:
            return {
                "current_price_source": "stored",
                "buffett_score": None,
                "moat": None,
                "signal": None,
                "opportunity_type": None,
            }
        price = result.get("current_price")
        if price is not None and price > 0:
            position.current_price = float(price)
        opportunity = best_opportunity(result)
        signal = generate_signal(
            dict(result, opportunity=opportunity), rank_score(result)
        )
        return {
            "current_price_source": "live",
            "buffett_score": result.get("buffett_score"),
            "moat": (result.get("moat_analysis") or {}).get("moat_type"),
            "signal": signal["signal"],
            "opportunity_type": opportunity["type"] if opportunity else None,
        }

    @staticmethod
    def _sector_map(portfolio: Portfolio) -> dict[str, str | None]:
        return {p.ticker: None for p in portfolio.positions}
