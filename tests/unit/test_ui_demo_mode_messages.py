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


def _open(monkeypatch, *, demo: bool) -> AppTest:
    if demo:
        monkeypatch.setenv("VI_DEMO", "1")
    else:
        monkeypatch.delenv("VI_DEMO", raising=False)
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def _run(monkeypatch, *, demo: bool, ticker: str) -> AppTest:
    at = _open(monkeypatch, demo=demo)
    next(field for field in at.text_input if field.label == "Ticker").set_value(ticker)
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def _run_multi(monkeypatch, *, demo: bool, tickers: str) -> AppTest:
    at = _open(monkeypatch, demo=demo)
    field = next(
        field
        for field in at.text_input
        if field.label.startswith("Multi-ticker compare")
    )
    field.set_value(tickers)
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def test_demo_mode_unsupported_ticker_lists_the_bundle(monkeypatch):
    at = _run(monkeypatch, demo=True, ticker="META")
    warnings = [warning.value for warning in at.warning]
    message = next(
        (
            w
            for w in warnings
            if "not in the demo bundle" in w and "Demo mode includes:" in w
        ),
        None,
    )
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


# ---------------------------------------------------------------------------
# Inline demo validation (caption + early warning + multi-ticker filter)
# ---------------------------------------------------------------------------
def test_demo_caption_lists_the_available_tickers(monkeypatch):
    at = _open(monkeypatch, demo=True)
    captions = [caption.value for caption in at.caption]
    message = next((c for c in captions if "available tickers are" in c), None)
    assert message is not None, captions
    for ticker in DEMO_TICKERS:
        assert ticker in message


def test_non_demo_page_shows_no_demo_caption(monkeypatch):
    at = _open(monkeypatch, demo=False)
    captions = [caption.value for caption in at.caption]
    assert not any("Demo mode: available tickers are" in c for c in captions)


def test_demo_single_input_warns_before_analyzing(monkeypatch):
    at = _open(monkeypatch, demo=True)
    next(field for field in at.text_input if field.label == "Ticker").set_value("META")
    at.run()
    warnings = [warning.value for warning in at.warning]
    message = next((w for w in warnings if "`META`" in w), None)
    assert message is not None, warnings
    assert "not in the demo bundle" in message
    for ticker in DEMO_TICKERS:
        assert ticker in message
    # The warning replaces the caption so the guidance is not repeated.
    captions = [caption.value for caption in at.caption]
    assert not any("available tickers are" in c for c in captions)


def test_demo_multi_ticker_lists_the_ignored_tickers(monkeypatch):
    at = _run_multi(monkeypatch, demo=True, tickers="AAPL, META")
    captions = [caption.value for caption in at.caption]
    ignored = next(
        (c for c in captions if "ignoring tickers without fixtures" in c), None
    )
    assert ignored is not None, captions
    assert "META" in ignored
    assert "AAPL" not in ignored


def test_demo_multi_ticker_with_only_unsupported_warns(monkeypatch):
    at = _run_multi(monkeypatch, demo=True, tickers="META, GOOGL")
    warnings = [warning.value for warning in at.warning]
    assert any("None of the requested tickers" in w for w in warnings)
    captions = [caption.value for caption in at.caption]
    ignored = next(
        (c for c in captions if "ignoring tickers without fixtures" in c), None
    )
    assert ignored is not None, captions
    assert "META" in ignored and "GOOGL" in ignored
