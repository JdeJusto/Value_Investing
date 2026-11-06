"""Single-ticker refresh wrapper over RefreshService."""

from __future__ import annotations

from backend.services.refresh_service import RefreshResult
from backend.services.ticker_refresh_service import refresh_ticker


class _FakeRefresh:
    def __init__(self, result: RefreshResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[list[str], dict]] = []

    def ensure_fresh_and_prices(self, tickers, **kwargs):
        self.calls.append((tickers, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_both_domains_success():
    fake = _FakeRefresh(RefreshResult(refreshed=["AAPL"], prices={"AAPL": 101.5}))

    result = refresh_ticker("aapl", service=fake)

    assert result.ticker == "AAPL"
    assert result.facts_synced is True
    assert result.prices_synced is True
    assert result.facts_error is None
    assert result.prices_error is None
    assert result.duration_seconds >= 0
    assert fake.calls[0][0] == ["AAPL"]
    assert fake.calls[0][1] == {
        "force": True,
        "skip_refresh": False,
        "fetch_prices": True,
    }


def test_facts_failure_is_reported():
    fake = _FakeRefresh(
        RefreshResult(
            failed=[("AAPL", "SEC down")],
            prices={"AAPL": 101.5},
        )
    )

    result = refresh_ticker("AAPL", service=fake)

    assert result.facts_synced is False
    assert result.facts_error == "SEC down"
    assert result.prices_synced is True


def test_missing_price_is_reported():
    fake = _FakeRefresh(RefreshResult(refreshed=["AAPL"], prices={"AAPL": None}))

    result = refresh_ticker("AAPL", service=fake)

    assert result.facts_synced is True
    assert result.prices_synced is False
    assert "Yahoo price unavailable" in (result.prices_error or "")


def test_prices_only_skips_sec():
    fake = _FakeRefresh(RefreshResult(skipped=["AAPL"], prices={"AAPL": 101.5}))

    result = refresh_ticker("AAPL", facts=False, prices=True, service=fake)

    assert result.facts_synced is False
    assert result.facts_error is None
    assert result.prices_synced is True
    assert fake.calls[0][1]["skip_refresh"] is True
    assert fake.calls[0][1]["fetch_prices"] is True


def test_exception_marks_requested_domains():
    fake = _FakeRefresh(RuntimeError("boom"))

    result = refresh_ticker("AAPL", service=fake)

    assert result.facts_synced is False
    assert result.prices_synced is False
    assert "RuntimeError" in (result.facts_error or "")
    assert "RuntimeError" in (result.prices_error or "")


def test_no_domain_does_not_call_service():
    fake = _FakeRefresh(RefreshResult())

    result = refresh_ticker("AAPL", facts=False, prices=False, service=fake)

    assert result.facts_synced is False
    assert result.prices_synced is False
    assert fake.calls == []
