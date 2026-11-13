"""Financial Modeling Prep provider (optional, requires ``FMP_API_KEY``).

Uses the legacy v3 endpoints documented by FMP. The free tier is small
(250 requests/day), so this provider is opt-in through ``PRICE_PROVIDER=fmp``;
any failure falls back to the next configured provider and, finally, Yahoo.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

from backend.services.price_providers.base import _bar, _iso_date

BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPProvider:
    name = "fmp"

    def __init__(self, api_key: str | None = None, *, timeout: float = 10.0) -> None:
        self.api_key = (api_key or os.environ.get("FMP_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("FMP_API_KEY is not set")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, object]) -> object:
        try:
            response = httpx.get(
                f"{BASE_URL}{path}",
                params={**params, "apikey": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 — re-raise without the key
            # httpx includes the request URL (and therefore the query key) in
            # some error messages; never let it reach a log.
            message = str(exc).replace(self.api_key, "***")
            raise RuntimeError(f"FMP request failed: {message}") from None

    def fetch_historical(
        self, ticker: str, start: str, end: str
    ) -> list[dict[str, object]]:
        data = self._get(
            f"/historical-price-full/{ticker.upper()}",
            {"from": start, "to": end},
        )
        rows = data.get("historical", []) if isinstance(data, dict) else []
        bars: list[dict[str, object]] = []
        # FMP returns newest-first; normalize ascending.
        for row in reversed(rows):
            when = _iso_date(row.get("date"))
            if when is None:
                continue
            bar = _bar(
                when,
                open_=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                close=row.get("adjClose", row.get("close")),
                volume=row.get("volume"),
            )
            if bar is not None:
                bars.append(bar)
        return bars

    def fetch_current(self, ticker: str) -> dict[str, object] | None:
        data = self._get(f"/quote/{ticker.upper()}", {})
        if not isinstance(data, list) or not data:
            return None
        quote = data[0]
        when = datetime.now(tz=UTC).date()
        return _bar(
            when,
            open_=quote.get("open"),
            high=quote.get("dayHigh"),
            low=quote.get("dayLow"),
            close=quote.get("price"),
            volume=quote.get("volume"),
        )
