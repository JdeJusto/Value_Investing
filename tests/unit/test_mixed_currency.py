"""Mixed-currency warnings: USD consumption and the [MIXED-CURRENCY] badge."""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Verdict
from backend.methodologies.common.company_type import company_flags
from backend.repositories.financial_database_repository import (
    FinancialDatabaseRepository,
)
from backend.services.methodology_ranking_service import RankedTicker
from backend.services.scorecard_service import NA, Scorecard, ScorecardService
from cli import theme
from cli.commands.rank import _single_dict
from cli.commands.scorecard import _badge_title


def _row(year: int = 2024, **overrides) -> NormalizedFinancials:
    data = {
        "ticker": "T",
        "fiscal_year": year,
        "revenue": 1000.0,
        "net_income": 120.0,
        "ebit": 150.0,
        "interest_expense": 20.0,
        "total_debt": 100.0,
        "stockholders_equity": 500.0,
        "cash_and_equivalents": 50.0,
        "free_cash_flow": 100.0,
        "tax_provision": 30.0,
        "pretax_income": 150.0,
        "currency": "USD",
    }
    data.update(overrides)
    return NormalizedFinancials(**data)


def test_company_flags_mixed_currency():
    assert company_flags(_row(currency="EUR")) == {"mixed_currency"}
    assert company_flags(_row(currency="GBP")) == {"mixed_currency"}
    assert company_flags(_row(currency="USD")) == set()
    # NULL/unknown is assumed USD: no badge.
    assert company_flags(_row(currency=None)) == set()


def test_merge_core_row_prefers_usd_columns():
    row = _row(currency="USD", revenue=100.0, net_income=10.0)
    core = {
        "currency": "EUR",
        "revenue": 100.0,
        "revenue_usd": 120.0,
        "net_income": 10.0,
        "net_income_usd": 12.0,
        "total_assets_usd": 1000.0,
        "stockholders_equity_usd": 400.0,
        "total_liabilities_usd": None,
        "cash_usd": 50.0,
    }

    merged = FinancialDatabaseRepository._merge_core_row(row, core)

    assert merged.revenue == 120.0
    assert merged.net_income == 12.0
    assert merged.total_assets == 1000.0
    assert merged.total_liabilities == 600.0  # derived in USD
    assert merged.cash_and_equivalents == 50.0
    assert merged.currency == "EUR"


def test_merge_core_row_clears_missing_non_usd_conversion():
    row = _row(currency="EUR", revenue=100.0)
    core = {"currency": "EUR", "revenue": 100.0, "revenue_usd": None}

    merged = FinancialDatabaseRepository._merge_core_row(row, core)

    # Do not leave the original EUR value in a field the analysis reads as USD.
    assert merged.revenue is None
    assert merged.currency == "EUR"


def test_merge_core_row_null_currency_is_usd():
    row = _row(currency="USD", revenue=100.0)
    core = {"currency": None, "revenue_usd": None}

    merged = FinancialDatabaseRepository._merge_core_row(row, core)

    assert merged.currency == "USD"
    assert merged.revenue == 100.0  # original USD value is safe


def test_theme_badge_label():
    text = theme.company_badges(("mixed_currency",))
    assert "[MIXED-CURRENCY]" in text


def test_cli_badge_title_contains_mixed_currency():
    card = Scorecard(
        ticker="SAN",
        company="Banco Santander",
        sector="Financial Services",
        industry="Banks",
        period="FY",
        price=5.0,
        market_cap=80_000.0,
        generated="",
        dimensions=(),
        overall="N/A",
        disagreements=(),
        methodologies=(),
        data_quality="HIGH",
        notes=(),
        overall_flags=("mixed_currency",),
    )

    assert "[MIXED-CURRENCY]" in _badge_title(card).plain


def test_rank_flags_include_mixed_currency():
    item = RankedTicker(
        ticker="SAN",
        verdict=Verdict.WATCH,
        score=70.0,
        family="DEEP_VALUE",
        n_a_reason=None,
        flags=("mixed_currency",),
    )
    assert _single_dict(item)["flags"] == ["mixed_currency"]


# ---------------------------------------------------------------------------
# Scorecard integration (fake repository; hermetic)
# ---------------------------------------------------------------------------
class _FakeRepository:
    def __init__(self, rows):
        self._rows = list(rows)

    def get_best_available(self, ticker, max_years=10):
        return list(self._rows)

    def get_company_name(self, ticker):
        return "Test Co"

    def list_all_facts(self, ticker, fiscal_period="FY", max_years=None):
        facts = []
        for row in self._rows:
            for concept, value in (
                ("Revenues", row.revenue),
                ("NetIncomeLoss", row.net_income),
                ("StockholdersEquity", row.stockholders_equity),
            ):
                if value is None:
                    continue
                facts.append(
                    {
                        "concept": concept,
                        "fiscal_year": row.fiscal_year,
                        "fiscal_period": "FY",
                        "value": float(value),
                        "unit": "USD",
                        "period_end": f"{row.fiscal_year}-12-31",
                        "namespace": "us-gaap",
                        "frame": None,
                    }
                )
        return facts


class _FakePrices:
    def get_current_price(self, ticker):
        return 10.0

    def get_market_cap(self, ticker):
        return 1_000.0


def _history(currency: str):
    return [
        _row(
            2020 + index,
            revenue=100.0 + 10 * index,
            net_income=10.0 + 2 * index,
            stockholders_equity=40.0 + 4 * index,
            currency=currency,
            sector="Industrials",
            industry="Widgets",
        )
        for index in range(6)
    ]


def test_scorecard_mixed_currency_flag_and_caption():
    card = ScorecardService(
        repository=_FakeRepository(_history("EUR")),
        price_service=_FakePrices(),
    ).build("SAN")

    assert card is not None
    assert "mixed_currency" in card.overall_flags
    assert any("Mixed currency" in note for note in card.notes)
    assert all("mixed_currency" in item["flags"] for item in card.methodologies)


def test_scorecard_usd_has_no_mixed_currency_flag():
    card = ScorecardService(
        repository=_FakeRepository(_history("USD")),
        price_service=_FakePrices(),
    ).build("AAPL")

    assert card is not None
    assert "mixed_currency" not in card.overall_flags
    assert not any("Mixed currency" in note for note in card.notes)


def test_scorecard_bank_can_carry_both_bank_and_mixed_currency():
    rows = _history("EUR")
    for row in rows:
        row.sector = "Financial Services"
        row.industry = "Banks - Diversified"
    card = ScorecardService(
        repository=_FakeRepository(rows),
        price_service=_FakePrices(),
    ).build("SAN")

    assert card is not None
    assert card.overall == NA
    assert {"bank", "mixed_currency"} <= set(card.overall_flags)
