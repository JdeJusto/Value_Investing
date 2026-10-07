"""Hermetic tests for the shared company-type detector.

``backend/methodologies/common/company_type.py`` is the single place that
decides whether a company is a FINANCIAL, REIT, UTILITY, HYPER_GROWTH,
STANDARD or UNKNOWN. Every methodology that guards on financials and the DCF
consume it, so the regression cases here mirror the previous private
heuristics (Lynch's balance-sheet signals + the DCF's bank fingerprint):
JPM/BAC-like rows are financial, AAPL/KO/F/MSFT-like rows are not.

No network, no database, no prices.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.company_type import (
    CompanyType,
    FinancialSubtype,
    detect_company_type,
    detect_financial_subtype,
    is_financial,
    is_hyper_growth,
    is_reit,
    is_utility,
)


def _row(year, **kwargs):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "currency": "USD",
        "source": "sec_edgar",
    }
    data.update(kwargs)
    return NormalizedFinancials.from_dict(data)


# ---------------------------------------------------------------------------
# sector hint
# ---------------------------------------------------------------------------
def test_sector_financial_services_is_financial():
    row = _row(2024, sector="Financial Services")
    assert detect_company_type(row, sector_hint=row.sector) is CompanyType.FINANCIAL
    assert is_financial(row, row.sector) is True


def test_sector_banks_and_insurance_are_financial():
    assert is_financial(None, "Banks") is True
    assert is_financial(None, "Banks—Diversified") is True
    assert is_financial(None, "Insurance") is True


def test_sector_real_estate_is_reit():
    row = _row(2024, sector="Real Estate")
    assert detect_company_type(row, sector_hint=row.sector) is CompanyType.REIT
    assert is_reit(row, row.sector) is True
    assert is_financial(row, row.sector) is False


def test_sector_utilities_is_utility():
    row = _row(2024, sector="Utilities")
    assert detect_company_type(row, sector_hint=row.sector) is CompanyType.UTILITY
    assert is_utility(row, row.sector) is True
    assert is_reit(row, row.sector) is False


def test_sector_hint_beats_balance_sheet_for_reit():
    # A REIT has no inventory and heavy debt — the raw balance sheet would
    # scream "financial"; the sector hint must win (decision order).
    row = _row(
        2024,
        sector="Real Estate",
        inventory=None,
        long_term_debt=20e9,
        net_income=1e9,
        total_assets=60e9,
        total_liabilities=50e9,
    )
    assert detect_company_type(row, sector_hint=row.sector) is CompanyType.REIT


def test_unknown_when_no_row_and_no_sector():
    assert detect_company_type() is CompanyType.UNKNOWN
    assert is_financial() is False
    assert is_reit() is False
    assert is_utility() is False


# ---------------------------------------------------------------------------
# balance-sheet / cash-flow fingerprint
# ---------------------------------------------------------------------------
def test_no_inventory_high_debt_is_financial():
    row = _row(
        2024,
        inventory=None,
        long_term_debt=60e9,
        net_income=10e9,
        revenue=40e9,
    )
    assert detect_company_type(row) is CompanyType.FINANCIAL
    assert is_financial(row) is True


def test_total_liabilities_over_85_percent_is_financial():
    row = _row(
        2024,
        total_assets=100e9,
        total_liabilities=88e9,
    )
    assert is_financial(row) is True


def test_known_non_financial_sector_beats_the_fingerprint():
    # Ford: tl/ta > 0.85 via Ford Credit; the sector says cyclical, so the
    # company is an automaker, not a bank. Without a sector the fingerprint
    # still applies.
    row = _row(
        2024,
        total_assets=285e9,
        total_liabilities=250e9,
    )
    assert is_financial(row) is True
    assert is_financial(row, "Consumer Cyclical") is False
    assert (
        detect_company_type(row, sector_hint="Consumer Cyclical")
        is CompanyType.STANDARD
    )


def test_bank_cash_flow_fingerprint_is_financial():
    # The JPM signature the DCF previously carried: positive net income,
    # non-positive operating cash flow, no capex, revenue present.
    row = _row(
        2025,
        revenue=182e9,
        net_income=55.7e9,
        operating_cash_flow=-147.8e9,
        capital_expenditure=None,
    )
    assert detect_company_type(row) is CompanyType.FINANCIAL
    assert is_financial(row) is True


def test_jpm_and_bac_like_rows_are_financial():
    # Bank-like leverage and no inventory (matches the old lynch detector).
    jpm = _row(
        2024,
        revenue=182e9,
        net_income=55.7e9,
        long_term_debt=300e9,
        total_assets=3.6e12,
        total_liabilities=3.27e12,
    )
    bac = _row(
        2024,
        revenue=98e9,
        net_income=30e9,
        long_term_debt=240e9,
        total_assets=3.3e12,
        total_liabilities=3.07e12,
    )
    assert is_financial(jpm) is True
    assert is_financial(bac) is True


# ---------------------------------------------------------------------------
# non-financial product companies stay untouched
# ---------------------------------------------------------------------------
def test_aapl_like_row_not_financial():
    row = _row(
        2024,
        revenue=390e9,
        net_income=97e9,
        inventory=6.5e9,
        long_term_debt=85e9,
        total_assets=350e9,
        total_liabilities=280e9,
        operating_cash_flow=118e9,
        capital_expenditure=11e9,
    )
    assert is_financial(row) is False
    assert detect_company_type(row) is CompanyType.STANDARD


def test_ko_f_msft_like_rows_not_financial():
    ko = _row(
        2024,
        revenue=45e9,
        net_income=9.8e9,
        inventory=4.4e9,
        long_term_debt=42e9,
        total_assets=100e9,
        total_liabilities=76e9,
        operating_cash_flow=11e9,
        capital_expenditure=2.3e9,
    )
    f = _row(
        2024,
        revenue=176e9,
        net_income=4.5e9,
        inventory=15e9,
        long_term_debt=19e9,
        total_assets=275e9,
        total_liabilities=228e9,
        operating_cash_flow=17e9,
        capital_expenditure=7.5e9,
    )
    msft = _row(
        2024,
        revenue=245e9,
        net_income=88e9,
        inventory=0.9e9,
        long_term_debt=42e9,
        total_assets=512e9,
        total_liabilities=249e9,
        operating_cash_flow=118e9,
        capital_expenditure=44e9,
    )
    for row in (ko, f, msft):
        assert is_financial(row) is False
        assert detect_company_type(row) is CompanyType.STANDARD


def test_product_company_with_positive_ocf_not_financial():
    row = _row(
        2024,
        revenue=100e9,
        net_income=15e9,
        operating_cash_flow=25e9,
        capital_expenditure=8e9,
        inventory=10e9,
        long_term_debt=20e9,
        total_assets=200e9,
        total_liabilities=120e9,
    )
    assert is_financial(row) is False


# ---------------------------------------------------------------------------
# hyper-growth
# ---------------------------------------------------------------------------
def _hyper_history(latest_fcf=-10.0):
    # 30% revenue CAGR 2019-2024 (100 -> 371.3), newest first.
    return [
        _row(2024, revenue=371.3, free_cash_flow=latest_fcf),
        _row(2023, revenue=285.6, free_cash_flow=5.0),
        _row(2022, revenue=219.7, free_cash_flow=4.0),
        _row(2021, revenue=169.0, free_cash_flow=3.0),
        _row(2020, revenue=130.0, free_cash_flow=2.0),
        _row(2019, revenue=100.0, free_cash_flow=1.0),
    ]


def test_high_cagr_with_negative_fcf_is_hyper_growth():
    rows = _hyper_history()
    assert detect_company_type(rows[0], rows) is CompanyType.HYPER_GROWTH
    assert is_hyper_growth(rows[0], rows) is True
    assert is_financial(rows[0]) is False


def test_high_cagr_with_positive_fcf_not_hyper_growth():
    rows = _hyper_history(latest_fcf=12.0)
    assert detect_company_type(rows[0], rows) is CompanyType.STANDARD
    assert is_hyper_growth(rows[0], rows) is False


def test_low_cagr_not_hyper_growth_even_when_burning_cash():
    rows = [
        _row(2024, revenue=110.0, free_cash_flow=-10.0),
        _row(2023, revenue=105.0, free_cash_flow=-5.0),
        _row(2022, revenue=100.0, free_cash_flow=-3.0),
    ]
    assert is_hyper_growth(rows[0], rows) is False


def test_financial_sector_beats_hyper_growth():
    rows = _hyper_history()
    row = _row(2024, sector="Financial Services", revenue=371.3, free_cash_flow=-10.0)
    assert detect_company_type(row, rows, row.sector) is CompanyType.FINANCIAL
    assert is_hyper_growth(row, rows, row.sector) is False


def test_revenue_cagr_fallback_from_ocf_minus_capex():
    # No direct free_cash_flow: the detector must use OCF - capex.
    rows = [
        _row(2024, revenue=371.3, operating_cash_flow=5.0, capital_expenditure=8.0),
        _row(2023, revenue=285.6, operating_cash_flow=5.0, capital_expenditure=5.0),
        _row(2022, revenue=219.7, operating_cash_flow=4.0, capital_expenditure=3.0),
        _row(2021, revenue=169.0, operating_cash_flow=3.0, capital_expenditure=2.0),
        _row(2020, revenue=130.0, operating_cash_flow=2.0, capital_expenditure=1.0),
        _row(2019, revenue=100.0, operating_cash_flow=1.0, capital_expenditure=1.0),
    ]
    result = detect_company_type(rows[0], rows)
    assert is_hyper_growth(rows[0], rows) is True
    assert result is CompanyType.HYPER_GROWTH


# ---------------------------------------------------------------------------
# financial subtype
# ---------------------------------------------------------------------------
def test_financial_subtype_from_sector_hint():
    assert (
        detect_financial_subtype(None, sector_hint="Banks—Diversified")
        is FinancialSubtype.BANK
    )
    assert (
        detect_financial_subtype(None, sector_hint="Credit Union")
        is FinancialSubtype.BANK
    )
    assert (
        detect_financial_subtype(None, sector_hint="Insurance")
        is FinancialSubtype.INSURANCE
    )
    assert (
        detect_financial_subtype(None, sector_hint="Reinsurance")
        is FinancialSubtype.INSURANCE
    )
    assert (
        detect_financial_subtype(None, sector_hint="Payment")
        is FinancialSubtype.PAYMENTS
    )
    assert (
        detect_financial_subtype(None, sector_hint="Asset Management")
        is FinancialSubtype.ASSET_MANAGEMENT
    )
    assert (
        detect_financial_subtype(None, sector_hint="Asset Manager")
        is FinancialSubtype.ASSET_MANAGEMENT
    )
    assert (
        detect_financial_subtype(None, sector_hint="Capital Markets")
        is FinancialSubtype.CAPITAL_MARKETS
    )
    assert (
        detect_financial_subtype(None, sector_hint="Broker")
        is FinancialSubtype.CAPITAL_MARKETS
    )
    assert (
        detect_financial_subtype(None, sector_hint="Exchange")
        is FinancialSubtype.CAPITAL_MARKETS
    )
    assert (
        detect_financial_subtype(None, sector_hint="Diversified Financial")
        is FinancialSubtype.FINANCIAL_OTHER
    )
    assert (
        detect_financial_subtype(None, sector_hint="Financial Services")
        is FinancialSubtype.FINANCIAL_OTHER
    )


def test_financial_subtype_falls_back_to_other_without_sector_hint():
    # A bank-like fingerprint with no sector hint -> FINANCIAL_OTHER
    row = _row(2024, inventory=None, long_term_debt=60e9, net_income=10e9, revenue=40e9)
    assert detect_financial_subtype(row) is FinancialSubtype.FINANCIAL_OTHER


def test_non_financial_returns_financial_other():
    row = _row(
        2024,
        revenue=390e9,
        inventory=6.5e9,
        operating_cash_flow=118e9,
        capital_expenditure=11e9,
    )
    assert detect_financial_subtype(row) is FinancialSubtype.FINANCIAL_OTHER


def test_reit_and_utility_return_financial_other():
    row_reit = _row(2024, sector="Real Estate")
    row_util = _row(2024, sector="Utilities")
    assert (
        detect_financial_subtype(row_reit, sector_hint=row_reit.sector)
        is FinancialSubtype.FINANCIAL_OTHER
    )
    assert (
        detect_financial_subtype(row_util, sector_hint=row_util.sector)
        is FinancialSubtype.FINANCIAL_OTHER
    )
