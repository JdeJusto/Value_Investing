"""Financial Modeling Prep provider (optional, requires ``FMP_API_KEY``).

Free accounts use FMP's *stable* API (the legacy v3 endpoints answer 403).
Historical bars come from ``historical-price-eod/dividend-adjusted`` so the
series is comparable with Yahoo's adjusted close. A v3 fallback keeps paid
legacy accounts working. Any failure falls back to the next provider and,
finally, Yahoo.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

from backend.services.price_providers.base import _bar, _iso_date

STABLE_URL = "https://financialmodelingprep.com/stable"
LEGACY_URL = "https://financialmodelingprep.com/api/v3"


class FMPProvider:
    name = "fmp"

    def __init__(self, api_key: str | None = None, *, timeout: float = 10.0) -> None:
        self.api_key = (api_key or os.environ.get("FMP_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("FMP_API_KEY is not set")
        self.timeout = timeout

    def _request(self, url: str, params: dict[str, object]) -> object:
        try:
            response = httpx.get(
                url,
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
        params = {"symbol": ticker.upper(), "from": start, "to": end}
        try:
            data = self._request(
                f"{STABLE_URL}/historical-price-eod/dividend-adjusted", params
            )
            rows = data if isinstance(data, list) else []
            return self._rows_to_bars(rows, adjusted=True)
        except RuntimeError:
            # Legacy paid accounts: v3 returns the rows wrapped in "historical".
            data = self._request(
                f"{LEGACY_URL}/historical-price-full/{ticker.upper()}",
                {"from": start, "to": end},
            )
            rows = data.get("historical", []) if isinstance(data, dict) else []
            return self._rows_to_bars(rows, adjusted=True)

    @staticmethod
    def _rows_to_bars(rows: list[dict], *, adjusted: bool) -> list[dict[str, object]]:
        bars: list[dict[str, object]] = []
        # FMP returns newest-first; normalize ascending.
        for row in reversed(rows):
            when = _iso_date(row.get("date"))
            if when is None:
                continue
            if adjusted and "adjClose" in row:
                open_ = row.get("adjOpen", row.get("open"))
                high = row.get("adjHigh", row.get("high"))
                low = row.get("adjLow", row.get("low"))
                close = row.get("adjClose")
            else:
                open_ = row.get("open")
                high = row.get("high")
                low = row.get("low")
                close = row.get("adjClose", row.get("close"))
            bar = _bar(
                when,
                open_=open_,
                high=high,
                low=low,
                close=close,
                volume=row.get("volume"),
            )
            if bar is not None:
                bars.append(bar)
        return bars

    def fetch_current(self, ticker: str) -> dict[str, object] | None:
        data: object
        try:
            data = self._request(f"{STABLE_URL}/quote", {"symbol": ticker.upper()})
        except RuntimeError:
            data = self._request(f"{LEGACY_URL}/quote/{ticker.upper()}", {})
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
