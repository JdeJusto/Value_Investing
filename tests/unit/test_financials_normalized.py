"""Unit tests for the normalized financials value object."""

from datetime import datetime, timezone, UTC

import pytest

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)


def test_to_dict_from_dict_roundtrip():
    record = NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=2025,
        revenue=394_328_000_000.0,
        net_income=96_995_000_000.0,
        shares_outstanding=15_220_000_000,
        source=ProviderName.YAHOO,
        loaded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    restored = NormalizedFinancials.from_dict(record.to_dict())

    assert restored.ticker == "AAPL"
    assert restored.fiscal_year == 2025
    assert restored.revenue == record.revenue
    assert restored.shares_outstanding == 15_220_000_000
    assert restored.source == ProviderName.YAHOO
    assert restored.loaded_at == record.loaded_at


def test_to_dict_serializes_source_and_date():
    record = NormalizedFinancials(
        ticker="MSFT",
        fiscal_year=2024,
        source=ProviderName.EDGAR,
        loaded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    data = record.to_dict()

    assert data["source"] == "edgar"
    assert data["loaded_at"] == "2026-01-01T00:00:00+00:00"
    assert data["ticker"] == "MSFT"


def test_from_dict_ignores_unknown_keys():
    record = NormalizedFinancials.from_dict(
        {"ticker": "GOOGL", "fiscal_year": 2023, "revenue": 307.4, "bogus": "x"}
    )
    assert record.revenue == 307.4
    assert not hasattr(record, "bogus")


def test_from_dict_missing_loaded_at_defaults():
    record = NormalizedFinancials.from_dict({"ticker": "AAPL", "fiscal_year": 2022})
    assert record.loaded_at is not None


def test_from_dict_invalid_source_falls_back():
    record = NormalizedFinancials.from_dict(
        {"ticker": "AAPL", "fiscal_year": 2022, "source": "unknown"}
    )
    assert record.source == ProviderName.YAHOO


@pytest.mark.parametrize(
    "fields",
    [
        {"income": object()},
        {"balance": object()},
        {"cash_flow": object()},
    ],
)
def test_raw_year_partial_data_is_not_empty(fields):
    from backend.domain.value_objects.financials_normalized import RawFinancialsYear

    raw = RawFinancialsYear(ticker="AAPL", year=2025, **fields)
    assert raw.is_empty() is False


def test_raw_year_empty():
    from backend.domain.value_objects.financials_normalized import RawFinancialsYear

    raw = RawFinancialsYear(ticker="AAPL", year=2025)
    assert raw.is_empty() is True
