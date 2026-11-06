"""AppTest for the Analysis refresh button (mocked service)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[2]


def test_refresh_button_calls_service_and_clears_cache(tmp_path, monkeypatch):
    cleared = []
    monkeypatch.setattr(st.cache_data, "clear", lambda: cleared.append(True))
    monkeypatch.setattr(st, "rerun", lambda: None)
    script = tmp_path / "refresh_app.py"
    script.write_text(
        f"""
import sys
from datetime import datetime
sys.path.insert(0, {str(REPO)!r})

import importlib
page = importlib.import_module("ui.pages.02_analysis")
from backend.services.ticker_refresh_service import TickerRefreshResult

calls = []

class Gateway:
    def resolve_company(self, ticker):
        return ("company-id", "cik")
    def last_synced_at(self, company_id):
        return datetime(2026, 11, 6, 12, 0)
    def close(self):
        pass

def fake_refresh(ticker, *, facts, prices):
    calls.append((ticker, facts, prices))
    return TickerRefreshResult(ticker, True, True, duration_seconds=0.1)

page.FdbGateway = Gateway
page.refresh_ticker = fake_refresh
page.is_demo = lambda: False
page._refresh_control("AAPL")
""",
        encoding="utf-8",
    )

    at = AppTest.from_file(str(script), default_timeout=60).run()

    assert not at.exception, at.exception
    assert any("Facts last updated: 2026-11-06 12:00" in c.value for c in at.caption)
    buttons = {button.label: button for button in at.button}
    assert "Refresh" in buttons

    buttons["Refresh"].click().run()

    assert not at.exception, at.exception
    assert any("Refreshed in 0.1s" in success.value for success in at.success)
    assert cleared


def test_refresh_button_shows_error_when_price_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "rerun", lambda: None)
    script = tmp_path / "refresh_error_app.py"
    script.write_text(
        f"""
import sys
from datetime import datetime
sys.path.insert(0, {str(REPO)!r})

import importlib
page = importlib.import_module("ui.pages.02_analysis")
from backend.services.ticker_refresh_service import TickerRefreshResult

class Gateway:
    def resolve_company(self, ticker):
        return ("company-id", "cik")
    def last_synced_at(self, company_id):
        return datetime(2026, 11, 6, 12, 0)
    def close(self):
        pass

page.FdbGateway = Gateway
page.refresh_ticker = lambda ticker, *, facts, prices: TickerRefreshResult(
    ticker, True, False, prices_error="Yahoo down"
)
page.is_demo = lambda: False
page._refresh_control("AAPL")
""",
        encoding="utf-8",
    )

    at = AppTest.from_file(str(script), default_timeout=60).run()

    buttons = {button.label: button for button in at.button}
    assert "Refresh" in buttons
    buttons["Refresh"].click().run()

    assert not at.exception, at.exception
    assert any("Refresh failed: Yahoo down" in error.value for error in at.error)
