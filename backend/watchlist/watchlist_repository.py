"""Watchlist persistence: load and save a Watchlist from a JSON file."""

import json
from abc import ABC, abstractmethod
from pathlib import Path

from backend.watchlist.models import Watchlist


class WatchlistRepository(ABC):
    @abstractmethod
    def load(self) -> Watchlist:
        """The stored watchlist (empty when nothing is stored yet)."""

    @abstractmethod
    def save(self, watchlist: Watchlist) -> None:
        """Persist the watchlist atomically."""


class JsonWatchlistRepository(WatchlistRepository):
    """File-backed watchlist at ``data/watchlist.json`` by default."""

    def __init__(self, path: str | Path = "data/watchlist.json"):
        self._path = Path(path)

    def load(self) -> Watchlist:
        if not self._path.exists():
            return Watchlist()
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                return Watchlist.from_dict(json.load(handle))
        except (json.JSONDecodeError, KeyError, ValueError):
            return Watchlist()

    def save(self, watchlist: Watchlist) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(watchlist.to_dict(), handle, indent=2)
        tmp.replace(self._path)
