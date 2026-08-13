"""Portfolio persistence: load and save a Portfolio from a JSON file."""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from backend.portfolio.models import Portfolio


class PortfolioRepository(ABC):
    @abstractmethod
    def load(self) -> Portfolio:
        """The stored portfolio (empty when nothing is stored yet)."""

    @abstractmethod
    def save(self, portfolio: Portfolio) -> None:
        """Persist the portfolio atomically."""


class JsonPortfolioRepository(PortfolioRepository):
    """File-backed portfolio at ``data/portfolio.json`` by default."""

    def __init__(self, path: str | os.PathLike = "data/portfolio.json"):
        self._path = Path(path)

    def load(self) -> Portfolio:
        if not self._path.exists():
            return Portfolio()
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                return Portfolio.from_dict(json.load(handle))
        except (json.JSONDecodeError, KeyError, ValueError):
            return Portfolio()

    def save(self, portfolio: Portfolio) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(portfolio.to_dict(), handle, indent=2)
        tmp.replace(self._path)
