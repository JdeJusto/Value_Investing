"""yfinance provider (no API key).

This is the default and the last-resort fallback. ``PriceService`` keeps its
own retry/throttle loop for the default path; this class exists so callers can
use the same provider interface explicitly and so the fallback chain is
uniform.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.services.price_providers.base import _bar


class YFinanceProvider:
    name = "yfinance"

    def fetch_historical(
        self, ticker: str, start: str, end: str
    ) -> list[dict[str, object]]:
        import yfinance as yf

        frame = yf.Ticker(ticker).history(start=start, end=end)
        return self._frame_to_bars(frame)

    def fetch_current(self, ticker: str) -> dict[str, object] | None:
        import yfinance as yf

        frame = yf.Ticker(ticker).history(period="5d")
        bars = self._frame_to_bars(frame)
        return bars[-1] if bars else None

    @staticmethod
    def _frame_to_bars(frame) -> list[dict[str, object]]:
        if frame is None or getattr(frame, "empty", True):
            return []
        bars: list[dict[str, object]] = []
        for index, row in frame.iterrows():
            when = (
                index.date() if hasattr(index, "date") else datetime.now(tz=UTC).date()
            )
            bar = _bar(
                when,
                open_=row.get("Open"),
                high=row.get("High"),
                low=row.get("Low"),
                close=row.get("Close"),
                volume=row.get("Volume"),
            )
            if bar is not None:
                bars.append(bar)
        return bars
