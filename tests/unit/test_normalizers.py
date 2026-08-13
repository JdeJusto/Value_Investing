"""Unit tests for Yahoo and EDGAR normalizers."""

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)
from backend.domain.value_objects.financials_normalized import (
    ProviderName,
    RawFinancialsYear,
)
from backend.providers.normalizers.edgar_normalizer import EdgarNormalizer
from backend.providers.normalizers.yahoo_normalizer import YahooNormalizer


def _yahoo_raw(**kw):
    return RawFinancialsYear(
        ticker="AAPL",
        year=2025,
        income=IncomeStatement(
            revenue=394_328,
            cogs=211_071,
            gross_profit=183_257,
            operating_income=123_216,
            ebit=123_216,
            ebitda=134_852,
            net_income=96_995,
            interest_expense=9_139,
            tax_provision=21_617,
            pretax_income=118_612,
        ),
        balance=BalanceSheet(
            total_assets=364_980,
            total_liabilities=293_505,
            total_debt=93_304,
            cash_and_equivalents=30_032,
            working_capital=-1_792,
            retained_earnings=4_432,
            stockholders_equity=71_475,
        ),
        cash_flow=CashFlowStatement(
            operating_cash_flow=118_254,
            capital_expenditure=9_870,
            free_cash_flow=108_384,
            depreciation_amortization=11_445,
            dividends_paid=15_533,
            repurchase_of_stock=76_683,
            working_capital_change=2_285,
        ),
        shares_outstanding=15_220_000_000,
        **kw,
    )


def test_yahoo_normalizer_maps_all_fields():
    normalized = YahooNormalizer().normalize(_yahoo_raw())

    assert normalized is not None
    assert normalized.ticker == "AAPL"
    assert normalized.fiscal_year == 2025
    assert normalized.source == ProviderName.YAHOO
    assert normalized.revenue == 394_328
    assert normalized.net_income == 96_995
    assert normalized.free_cash_flow == 108_384
    assert normalized.total_assets == 364_980
    assert normalized.total_liabilities == 293_505
    assert normalized.shares_outstanding == 15_220_000_000
    assert normalized.ebitda == 134_852


def test_yahoo_normalizer_derives_ebitda_and_fcf():
    raw = _yahoo_raw()
    raw.income = IncomeStatement(revenue=100, ebit=40, net_income=25)
    raw.cash_flow = CashFlowStatement(
        operating_cash_flow=30, capital_expenditure=10, depreciation_amortization=5
    )

    normalized = YahooNormalizer().normalize(raw)

    assert normalized.ebitda == 45  # ebit + depreciation
    assert normalized.free_cash_flow == 30 - 10
    assert normalized.operating_cash_flow == 30


def test_yahoo_normalizer_empty_year_returns_none():
    assert (
        YahooNormalizer().normalize(RawFinancialsYear(ticker="AAPL", year=2025)) is None
    )


def test_edgar_normalizer_maps_available_fields():
    raw = RawFinancialsYear(
        ticker="MSFT",
        year=2024,
        income=IncomeStatement(
            revenue=245_122, ebit=109_435, operating_income=109_435, net_income=88_136
        ),
        balance=BalanceSheet(
            total_assets=512_163,
            total_liabilities=264_035,
            stockholders_equity=248_128,
        ),
        cash_flow=CashFlowStatement(operating_cash_flow=118_548, free_cash_flow=85_968),
    )

    normalized = EdgarNormalizer().normalize(raw)

    assert normalized is not None
    assert normalized.source == ProviderName.EDGAR
    assert normalized.revenue == 245_122
    assert normalized.ebit == 109_435
    assert normalized.total_assets == 512_163
    assert normalized.stockholders_equity == 248_128
    assert normalized.free_cash_flow == 85_968
    assert normalized.operating_cash_flow == 118_548
    assert normalized.cogs is None


def test_edgar_normalizer_derives_fcf_when_missing():
    raw = RawFinancialsYear(
        ticker="MSFT",
        year=2024,
        income=IncomeStatement(revenue=245_122, net_income=88_136),
        cash_flow=CashFlowStatement(operating_cash_flow=100, capital_expenditure=25),
    )

    normalized = EdgarNormalizer().normalize(raw)

    assert normalized.free_cash_flow == 75


def test_edgar_normalizer_empty_year_returns_none():
    assert (
        EdgarNormalizer().normalize(RawFinancialsYear(ticker="MSFT", year=2024)) is None
    )
