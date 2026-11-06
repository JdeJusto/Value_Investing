"""CLI `refresh` command and exit-code contract."""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.services.ticker_refresh_service import TickerRefreshResult
from cli.commands import refresh


def _args(**overrides):
    data = {
        "ticker": "AAPL",
        "facts_only": False,
        "prices_only": False,
        "json": False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_facts_only_success(monkeypatch, capsys):
    called = {}

    def fake(ticker, *, facts, prices):
        called.update(ticker=ticker, facts=facts, prices=prices)
        return TickerRefreshResult(ticker, True, False)

    monkeypatch.setattr(refresh, "refresh_ticker", fake)
    code = refresh.run(_args(facts_only=True))

    assert code == 0
    assert called == {"ticker": "AAPL", "facts": True, "prices": False}
    out = capsys.readouterr().out
    assert "Facts:  OK" in out


def test_facts_only_failure_is_total(monkeypatch, capsys):
    monkeypatch.setattr(
        refresh,
        "refresh_ticker",
        lambda ticker, *, facts, prices: TickerRefreshResult(
            ticker, False, False, facts_error="SEC down"
        ),
    )

    assert refresh.run(_args(facts_only=True)) == 2
    assert "SEC down" in capsys.readouterr().out


def test_both_domains_partial(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "refresh_ticker",
        lambda ticker, *, facts, prices: TickerRefreshResult(
            ticker, True, False, prices_error="Yahoo down"
        ),
    )

    assert refresh.run(_args()) == 1


def test_both_domains_total_failure(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "refresh_ticker",
        lambda ticker, *, facts, prices: TickerRefreshResult(ticker, False, False),
    )

    assert refresh.run(_args()) == 2


def test_json_shape(monkeypatch, capsys):
    monkeypatch.setattr(
        refresh,
        "refresh_ticker",
        lambda ticker, *, facts, prices: TickerRefreshResult(
            ticker, True, True, duration_seconds=0.25
        ),
    )

    code = refresh.run(_args(json=True))
    data = json.loads(capsys.readouterr().out)

    assert code == 0
    assert data == {
        "ticker": "AAPL",
        "facts_synced": True,
        "prices_synced": True,
        "facts_error": None,
        "prices_error": None,
        "duration_seconds": 0.25,
    }


def test_prices_only_success_prints_note(monkeypatch, capsys):
    called = {}

    def fake(ticker, *, facts, prices):
        called.update(facts=facts, prices=prices)
        return TickerRefreshResult(ticker, False, True)

    monkeypatch.setattr(refresh, "refresh_ticker", fake)
    code = refresh.run(_args(prices_only=True))

    assert code == 0
    assert called == {"facts": False, "prices": True}
    out = capsys.readouterr().out
    assert "not persisted to FDB" in out


def test_prices_only_failure_is_total(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "refresh_ticker",
        lambda ticker, *, facts, prices: TickerRefreshResult(
            ticker, False, False, prices_error="Yahoo down"
        ),
    )

    assert refresh.run(_args(prices_only=True)) == 2


def test_both_flags_rejected_without_calling_service(monkeypatch, capsys):
    called = False

    def fake(*_args, **_kwargs):
        nonlocal called
        called = True
        return TickerRefreshResult("AAPL", True, True)

    monkeypatch.setattr(refresh, "refresh_ticker", fake)
    code = refresh.run(_args(facts_only=True, prices_only=True))

    assert code == 2
    assert called is False
    assert "at most one" in capsys.readouterr().err
