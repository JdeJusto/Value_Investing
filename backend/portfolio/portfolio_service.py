"""Portfolio service: tracks positions and connects them to intelligence.

The analyzer is the analytics-layer entry point (it may refresh prices
and scores); the service itself never touches providers directly.
"""

from collections.abc import Callable
from datetime import datetime, timezone

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
        portfolio = self._load()
        t = ticker.upper().strip()
        position = Position(
            ticker=t,
            quantity=quantity,
            avg_price=avg_price,
            current_price=avg_price,
            entry_date=entry_date or datetime.now(timezone.utc),
            thesis=thesis,
            signal_at_entry=signal_at_entry,
        )
        portfolio.add(position)
        self._save(portfolio)
        return position

    def exit(self, ticker: str, price: float) -> Position | None:
        """Close a position at ``price`` and record realized PnL."""
        portfolio = self._load()
        closed = portfolio.close(ticker, price)
        if closed is not None:
            self._save(portfolio)
        return closed

    def remove(self, ticker: str) -> Position | None:
        portfolio = self._load()
        removed = portfolio.remove(ticker)
        if removed is not None:
            self._save(portfolio)
        return removed

    # ------------------------------------------------------------------
    def view(self) -> list[dict]:
        """Every open position enriched with scores, moat and signal."""
        portfolio = self._load()
        self._refresh_prices(portfolio)
        self._save(portfolio)
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
        portfolio = self._load()
        self._refresh_prices(portfolio)
        self._save(portfolio)
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
