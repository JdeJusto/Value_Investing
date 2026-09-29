"""Watchlist domain models: companies under monitoring with a status.

Items carry the reason they are watched (thesis) and transition through
statuses: MONITORING -> BOUGHT (moved to the portfolio) or DISCARDED.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

MONITORING = "MONITORING"
BOUGHT = "BOUGHT"
DISCARDED = "DISCARDED"
STATUSES = (MONITORING, BOUGHT, DISCARDED)


@dataclass(slots=True)
class WatchlistItem:
    ticker: str
    status: str = MONITORING
    added_at: datetime = field(default_factory=datetime.now)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = dict(asdict(self))
        data["added_at"] = self.added_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "WatchlistItem":
        return cls(
            ticker=data["ticker"].upper().strip(),
            status=data.get("status", MONITORING),
            added_at=(
                datetime.fromisoformat(data["added_at"])
                if data.get("added_at")
                else datetime.now()
            ),
            note=data.get("note", ""),
        )


@dataclass(slots=True)
class Watchlist:
    name: str = "default"
    items: list[WatchlistItem] = field(default_factory=list)

    def item(self, ticker: str) -> WatchlistItem | None:
        for item in self.items:
            if item.ticker == ticker.upper().strip():
                return item
        return None

    def add(self, item: WatchlistItem) -> None:
        """Insert or replace an item for the same ticker."""
        existing = self.item(item.ticker)
        if existing is not None:
            existing.status = item.status
            existing.note = item.note
            return
        self.items.append(item)

    def remove(self, ticker: str) -> WatchlistItem | None:
        found = self.item(ticker)
        if found is not None:
            self.items.remove(found)
        return found

    def set_status(self, ticker: str, status: str) -> WatchlistItem | None:
        if status not in STATUSES:
            raise ValueError(f"unknown watchlist status '{status}'")
        item = self.item(ticker)
        if item is None:
            return None
        item.status = status
        return item

    def monitoring(self) -> list[WatchlistItem]:
        return [i for i in self.items if i.status == MONITORING]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Watchlist":
        return cls(
            name=data.get("name", "default"),
            items=[WatchlistItem.from_dict(i) for i in data.get("items", [])],
        )
