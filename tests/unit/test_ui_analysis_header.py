"""The Analysis page's pinned price/market-cap header (visible in all tabs)."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def _header_metrics(at) -> dict[str, str]:
    """The first three metrics on the page are the pinned header."""
    return {metric.label: metric.value for metric in at.metric[:3]}


def test_header_shows_price_market_cap_and_sector(monkeypatch):
    import backend.services.price_service as price_module
    from ui import services

    # The price service is a process-level singleton created on first use; an
    # earlier non-demo test may have cached a real one (and its quote). Reset
    # both so this test exercises the demo fixture deterministically.
    services.load_quote.clear()
    monkeypatch.setattr(price_module, "_PRICE_SERVICE", None)

    at = _run(monkeypatch)
    metrics = _header_metrics(at)
    assert list(metrics) == ["Precio", "Market Cap", "Sector"]
    assert metrics["Precio"] == "$340.00"  # demo AAPL price
    assert metrics["Market Cap"].endswith("T")  # abbreviated
    assert metrics["Sector"]  # from the VO (or "—")


def test_header_market_cap_uses_abbreviation(monkeypatch):
    at = _run(monkeypatch)
    metrics = _header_metrics(at)
    assert metrics["Market Cap"].startswith("$")
    assert any(metrics["Market Cap"].endswith(suffix) for suffix in ("B", "T"))
    assert "," not in metrics["Market Cap"]  # abbreviated, no raw separators


def test_header_survives_a_missing_quote(monkeypatch):
    from ui import services

    monkeypatch.setattr(
        services,
        "load_quote",
        lambda ticker: {"price": None, "market_cap": None},
    )
    at = _run(monkeypatch)
    metrics = _header_metrics(at)
    assert metrics["Precio"] == "—"
    assert metrics["Market Cap"] == "—"
    # The rest of the page still renders.
    assert any(tab.label == "Financials" for tab in at.tabs)


def test_header_is_pinned_above_the_tabs(monkeypatch):
    at = _run(monkeypatch)
    # The header metrics come before every tab's content in the element tree
    # (the Overview repeats the same labels later; the header is first).
    assert [metric.label for metric in at.metric[:3]] == [
        "Precio",
        "Market Cap",
        "Sector",
    ]
    # The Financials content renders in the same run, so the header stays
    # visible while browsing the tab.
    assert any(expander.label == "Summary" for expander in at.expander)
