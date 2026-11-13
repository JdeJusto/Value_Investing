"""Tiingo provider (optional, requires ``TIINGO_API_KEY``).

Tiingo's daily endpoint is generous on the free tier (1,000 requests/day) and
returns adjusted OHLCV. The key travels in the ``Authorization`` header, never
in the query string.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx

from backend.services.price_providers.base import _bar, _iso_date

BASE_URL = "https://api.tiingo.com/tiingo/daily"


class TiingoProvider:
    name = "tiingo"

    def __init__(self, api_key: str | None = None, *, timeout: float = 10.0) -> None:
        self.api_key = (api_key or os.environ.get("TIINGO_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("TIINGO_API_KEY is not set")
        self.timeout = timeout

    def _get(self, ticker: str, params: dict[str, object]) -> object:
        try:
            response = httpx.get(
                f"{BASE_URL}/{ticker.upper()}/prices",
                params=params,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 — re-raise without the key
            message = str(exc).replace(self.api_key, "***")
            raise RuntimeError(f"Tiingo request failed: {message}") from None

    def fetch_historical(
        self, ticker: str, start: str, end: str
    ) -> list[dict[str, object]]:
        data = self._get(ticker, {"startDate": start, "endDate": end})
        if not isinstance(data, list):
            return []
        bars: list[dict[str, object]] = []
        for row in data:
            when = _iso_date(row.get("date"))
            if when is None:
                continue
            bar = _bar(
                when,
                open_=row.get("adjOpen", row.get("open")),
                high=row.get("adjHigh", row.get("high")),
                low=row.get("adjLow", row.get("low")),
                close=row.get("adjClose", row.get("close")),
                volume=row.get("adjVolume", row.get("volume")),
            )
            if bar is not None:
                bars.append(bar)
        return bars

    def fetch_current(self, ticker: str) -> dict[str, object] | None:
        end = datetime.now(tz=UTC).date()
        start = end - timedelta(days=7)
        bars = self.fetch_historical(ticker, start.isoformat(), end.isoformat())
        return bars[-1] if bars else None
