"""Unit tests for data freshness, completeness and quality scoring."""

from datetime import datetime, timedelta, timezone, UTC

import pytest

from backend.domain.services.data_freshness import is_stale, needs_refresh
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.providers.normalizers.quality import (
    REQUIRED_FIELDS,
    apply_quality_metrics,
    compute_completeness,
)


def _record(
    source: ProviderName = ProviderName.YAHOO,
    stale_by_age: bool = False,
    completeness_fields=None,
    quality: float | None = None,
) -> NormalizedFinancials:
    fields = completeness_fields or {
        "revenue": 100.0,
        "net_income": 20.0,
        "total_assets": 300.0,
        "shares_outstanding": 1_000_000,
        "free_cash_flow": 15.0,
        "ebitda": 30.0,
    }
    loaded_at = datetime.now(UTC) - (
        timedelta(days=100) if stale_by_age else timedelta(days=1)
    )
    record = NormalizedFinancials(
        ticker="AAPL",
        fiscal_year=2025,
        source=source,
        loaded_at=loaded_at,
        **fields,
    )
    apply_quality_metrics(record)
    if quality is not None:
        record.data_quality_score = quality
    return record


# ------------------------------------------------------------------ completeness


def test_completeness_full():
    assert compute_completeness(_record()) == 1.0


def test_completeness_missing_one_required_field():
    record = _record(
        completeness_fields={
            "revenue": 100.0,
            "net_income": 20.0,
            "total_assets": None,
            "shares_outstanding": 1_000_000,
        }
    )
    assert compute_completeness(record) == 0.75
    assert record.is_complete is False


def test_completeness_required_fields_are_exact_set():
    assert REQUIRED_FIELDS == (
        "revenue",
        "net_income",
        "total_assets",
        "shares_outstanding",
    )


# ------------------------------------------------------------------ quality score


def test_yahoo_complete_scores_1():
    record = _record(source=ProviderName.YAHOO)
    # 0.5 * 1.0 (completeness) + 0.3 * 1.0 (reliability) + 0.2 * 1.0 (derived present)
    assert record.data_quality_score == pytest.approx(1.0)


def test_edgar_complete_scores_below_yahoo():
    yahoo = _record(source=ProviderName.YAHOO)
    edgar = _record(source=ProviderName.EDGAR)
    assert edgar.data_quality_score < yahoo.data_quality_score
    assert edgar.data_quality_score == pytest.approx(0.94)


def test_quality_score_drops_with_incomplete_data():
    record = _record(
        source=ProviderName.YAHOO,
        completeness_fields={
            "revenue": 100.0,
            "net_income": None,
            "total_assets": 300.0,
            "shares_outstanding": None,
            "free_cash_flow": 15.0,
            "ebitda": 30.0,
        },
    )
    # 0.5 * 0.5 + 0.3 * 1.0 + 0.2 * 1.0 = 0.75
    assert record.data_quality_score == pytest.approx(0.75)


def test_data_source_priority_mapped():
    assert _record(source=ProviderName.YAHOO).data_source_priority == 2
    assert _record(source=ProviderName.EDGAR).data_source_priority == 1


def test_quality_applied_by_normalizer_marks_derived_fcf():
    from backend.domain.entities.financials import (
        BalanceSheet,
        CashFlowStatement,
        IncomeStatement,
    )
    from backend.domain.value_objects.financials_normalized import RawFinancialsYear
    from backend.providers.normalizers.edgar_normalizer import EdgarNormalizer

    raw = RawFinancialsYear(
        ticker="MSFT",
        year=2024,
        income=IncomeStatement(revenue=245_122, net_income=88_136),
        balance=BalanceSheet(total_assets=512_163),
        cash_flow=CashFlowStatement(operating_cash_flow=100, capital_expenditure=25),
        shares_outstanding=7_430_000_000,
    )
    normalized = EdgarNormalizer().normalize(raw)

    assert normalized.free_cash_flow == 75
    assert "free_cash_flow" in normalized.derived_metrics
    assert normalized.data_completeness == 1.0
    assert normalized.is_complete is True
    # 0.5 * 1.0 + 0.3 * 0.8 + 0.2 * 0.5 (ebitda missing)
    assert normalized.data_quality_score == pytest.approx(0.84)


# ------------------------------------------------------------------ freshness


def test_fresh_record_is_not_stale():
    assert is_stale(_record()) is False


def test_old_record_is_stale():
    assert is_stale(_record(stale_by_age=True)) is True


def test_low_quality_record_is_stale_even_if_recent():
    record = _record(quality=0.6)
    assert is_stale(record) is True


def test_missing_loaded_at_is_stale():
    record = NormalizedFinancials(ticker="AAPL", fiscal_year=2025, loaded_at=None)
    assert is_stale(record) is True


def test_needs_refresh_empty_history():
    assert needs_refresh([]) is True


def test_needs_refresh_all_fresh():
    assert needs_refresh([_record(), _record()]) is False


def test_needs_refresh_single_stale_record():
    assert needs_refresh([_record(), _record(stale_by_age=True)]) is True


def test_quality_fields_survive_roundtrip():
    record = _record(source=ProviderName.EDGAR)
    record.derived_metrics = ["free_cash_flow"]

    restored = NormalizedFinancials.from_dict(record.to_dict())

    assert restored.data_quality_score == record.data_quality_score
    assert restored.data_completeness == record.data_completeness
    assert restored.is_complete == record.is_complete
    assert restored.data_source_priority == record.data_source_priority
    assert restored.derived_metrics == ["free_cash_flow"]
    assert restored.source == ProviderName.EDGAR
