"""Demo-mode UX: mode-aware messages when a ticker has no fundamentals."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend.services.demo_mode import DEMO_TICKERS

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


@pytest.fixture(autouse=True)
def _clear_ui_state(monkeypatch):
    """Isolate the page from caches and a previously created price service."""
    import backend.services.price_service as price_module
    from ui import services

    services.load_fundamentals.clear()
    services.load_quote.clear()
    monkeypatch.setattr(price_module, "_PRICE_SERVICE", None)
    yield


def _run(monkeypatch, *, demo: bool, ticker: str) -> AppTest:
    if demo:
        monkeypatch.setenv("VI_DEMO", "1")
    else:
        monkeypatch.delenv("VI_DEMO", raising=False)
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(field for field in at.text_input if field.label == "Ticker").set_value(ticker)
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def test_demo_mode_unsupported_ticker_lists_the_bundle(monkeypatch):
    at = _run(monkeypatch, demo=True, ticker="META")
    warnings = [warning.value for warning in at.warning]
    message = next((w for w in warnings if "not in the demo bundle" in w), None)
    assert message is not None, warnings
    assert "`META`" in message
    for ticker in DEMO_TICKERS:
        assert ticker in message
    assert "VI_DEMO=1" in message


def test_demo_supported_ticker_with_empty_fixture_reports_a_bug(monkeypatch):
    from ui import services

    monkeypatch.setattr(services, "load_fundamentals", lambda ticker: [])
    at = _run(monkeypatch, demo=True, ticker="AAPL")
    errors = [error.value for error in at.error]
    message = next((e for e in errors if "returned no data" in e), None)
    assert message is not None, errors
    assert "`AAPL`" in message
    assert "bug" in message.lower()


def test_production_missing_ticker_points_to_financial_database(monkeypatch):
    from ui import services

    monkeypatch.setattr(services, "load_fundamentals", lambda ticker: [])
    at = _run(monkeypatch, demo=False, ticker="META")
    warnings = [warning.value for warning in at.warning]
    message = next((w for w in warnings if "No fundamentals found" in w), None)
    assert message is not None, warnings
    assert "`META`" in message
    assert "Financial-DataBase" in message


def test_none_of_the_new_messages_are_in_spanish(monkeypatch):
    at = _run(monkeypatch, demo=True, ticker="META")
    rendered = " ".join(element.value for element in [*at.warning, *at.error, *at.info])
    for fragment in ("No hay", "no hay", "Sin fundamentales", "sin fundamentales"):
        assert fragment not in rendered
