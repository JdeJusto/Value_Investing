"""Unit tests for ``ScorecardChartService`` (the Scorecard tab's charts).

The service is a read-only adapter: it reuses the analytics calculators and
the DCF, so these tests pin the series shape, the ordering/filtering rules and
the "missing price degrades, never crashes" behaviour.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.services.scorecard_charts_service import ScorecardChartService


class _Repo:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple[str, int | None]] = []

    def get_best_available(self, ticker, max_years=None):
        self.calls.append((ticker, max_years))
        return self._rows


class _BoomRepo:
    def get_best_available(self, ticker, max_years=None):
        raise RuntimeError("database offline")


class _BoomPrice:
    def get_current_price(self, ticker):
        raise RuntimeError("no network")

    def get_shares_outstanding(self, ticker):
        raise RuntimeError("no network")


def _row(year: int, *, revenue: float | None = 100.0, cogs: float | None = 60.0):
    return NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=year,
        revenue=revenue,
        cogs=cogs,
        operating_income=25.0 if revenue is not None else None,
        ebit=25.0 if revenue is not None else None,
        net_income=20.0 if revenue is not None else None,
        total_debt=50.0,
        cash_and_equivalents=20.0,
        stockholders_equity=100.0,
    )


def test_series_are_sorted_ascending_and_computed_from_calculators():
    # Repository order is newest-first, as the real repositories return it.
    repo = _Repo([_row(2025), _row(2024)])
    charts = ScorecardChartService(repo, price_service=None).build("aapl")

    assert charts is not None
    assert charts.ticker == "AAPL"
    assert [year.fiscal_year for year in charts.years] == [2024, 2025]

    latest = charts.years[-1]
    assert latest.revenue == 100.0
    assert latest.net_income == 20.0
    assert latest.gross_margin == 0.4  # (100 - 60) / 100
    assert latest.operating_margin == 0.25
    assert latest.net_margin == 0.2
    assert latest.roe == 0.2  # 20 / 100
    assert latest.roic is not None


def test_all_empty_and_none_rows_are_dropped():
    repo = _Repo([_row(2024), None, _row(2025, revenue=None)])
    charts = ScorecardChartService(repo, price_service=None).build("AAPL")

    assert charts is not None
    assert [year.fiscal_year for year in charts.years] == [2024]


def test_no_fundamentals_returns_none():
    assert ScorecardChartService(_Repo([]), price_service=None).build("AAPL") is None


def test_repository_failure_returns_none_instead_of_raising():
    assert ScorecardChartService(_BoomRepo(), price_service=None).build("AAPL") is None


def test_dcf_failure_degrades_to_none_but_keeps_the_series():
    charts = ScorecardChartService(
        _Repo([_row(2025)]), price_service=_BoomPrice()
    ).build("AAPL")

    assert charts is not None
    assert len(charts.years) == 1
    assert charts.dcf_value is None
    assert charts.price is None


def test_payload_serializes_to_a_plain_dict():
    charts = ScorecardChartService(_Repo([_row(2025)]), price_service=None).build(
        "AAPL"
    )
    payload = charts.to_dict()

    assert payload["ticker"] == "AAPL"
    assert payload["years"][0]["fiscal_year"] == 2025
    assert payload["dcf_value"] is None
    assert payload["price"] is None
