"""Portfolio domain models: positions with their investment thesis.

A position remembers why it was bought (thesis + signal at entry) so
the portfolio answers "what do I hold and why do I hold it".
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(slots=True)
class Position:
    ticker: str
    quantity: float
    avg_price: float
    current_price: float
    entry_date: datetime
    thesis: str = ""
    signal_at_entry: str = ""
    exit_date: datetime | None = None
    exit_price: float | None = None

    # --- computed shortcuts ------------------------------------------
    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_price) * self.quantity

    @property
    def realized_pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.avg_price) * self.quantity

    @property
    def unrealized_return(self) -> float | None:
        if self.avg_price == 0:
            return None
        return (self.current_price - self.avg_price) / self.avg_price

    # --- serialization ------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = dict(asdict(self))
        data["entry_date"] = self.entry_date.isoformat()
        data["exit_date"] = (
            self.exit_date.isoformat() if self.exit_date is not None else None
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position":
        known = {
            "ticker",
            "quantity",
            "avg_price",
            "current_price",
            "thesis",
            "signal_at_entry",
        }
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if key in known:
                clean[key] = value
        clean["entry_date"] = datetime.fromisoformat(str(data["entry_date"]))
        if data.get("exit_date"):
            clean["exit_date"] = datetime.fromisoformat(str(data["exit_date"]))
        if data.get("exit_price") is not None:
            clean["exit_price"] = data["exit_price"]
        return cls(**clean)


@dataclass(slots=True)
class Portfolio:
    """A named collection of positions."""

    name: str = "default"
    positions: list[Position] = field(default_factory=list)

    def position(self, ticker: str) -> Position | None:
        for p in self.positions:
            if p.ticker.upper() == ticker.upper() and p.is_open:
                return p
        return None

    def add(self, position: Position) -> None:
        existing = self.position(position.ticker)
        if existing is not None:
            self.merge(existing, position)
            return
        self.positions.append(position)

    @staticmethod
    def merge(existing: Position, addition: Position) -> None:
        """Average-in: combine two buys of the same ticker."""
        total_quantity = existing.quantity + addition.quantity
        if total_quantity == 0:
            return
        existing.avg_price = (
            existing.avg_price * existing.quantity
            + addition.avg_price * addition.quantity
        ) / total_quantity
        existing.quantity = total_quantity
        if not existing.thesis and addition.thesis:
            existing.thesis = addition.thesis

    def remove(self, ticker: str) -> Position | None:
        for p in self.positions:
            if p.ticker.upper() == ticker.upper():
                self.positions.remove(p)
                return p
        return None

    def close(
        self, ticker: str, price: float, exit_date: datetime | None = None
    ) -> Position | None:
        position = self.position(ticker)
        if position is None:
            return None
        position.exit_price = price
        position.exit_date = exit_date or datetime.now()
        return position

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "positions": [p.to_dict() for p in self.positions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        return cls(
            name=data.get("name", "default"),
            positions=[Position.from_dict(p) for p in data.get("positions", [])],
        )
