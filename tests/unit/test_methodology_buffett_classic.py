"""Tests for the buffett_classic methodology (20-rule weighted framework)."""

from __future__ import annotations

from types import SimpleNamespace

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.buffett_classic import BuffettClassicMethodology
from backend.methodologies.buffett_classic import methodology as methodology_module


class _Prices:
    def get_current_price(self, ticker):
        return 4.0


class _ExplodingPrices:
    def get_current_price(self, ticker):
        return 4.0

    def get_beta(self, ticker):
        raise RuntimeError("no beta")


def _row(year: int, **overrides):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "currency": "USD",
        "source": "sec_edgar",
        "shares_outstanding": 100,
        "split_adjustment_factor": 1.0,
        "sector": "Industrials",
    }
    data.update(overrides)
    return NormalizedFinancials.from_dict(data)


def _strong_rows():
    rows = []
    for index in range(5):
        growth = 1.05 ** (4 - index)
        rows.append(
            _row(
                2025 - index,
                revenue=100 * growth,
                gross_profit=60 * growth,
                ebit=40 * growth,
                operating_income=40 * growth,
                net_income=25 * growth,
                free_cash_flow=21 * growth,
                depreciation_amortization=5,
                capital_expenditure=2,
                total_debt=20,
                stockholders_equity=100,
                cash_and_equivalents=10,
                current_assets=200,
                current_liabilities=100,
                interest_expense=1,
                tax_provision=0,
                pretax_income=100,
                shares_outstanding=100 - (4 - index),
                repurchase_of_stock=1,
                research_development=5,
            )
        )
    return rows


def _weak_rows():
    rows = []
    for index in range(5):
        rows.append(
            _row(
                2025 - index,
                revenue=100,
                gross_profit=10,
                ebit=5,
                operating_income=5,
                net_income=2,
                free_cash_flow=-5,
                capital_expenditure=10,
                total_debt=300,
                stockholders_equity=100,
                current_assets=50,
                current_liabilities=100,
                interest_expense=20,
                tax_provision=0,
                pretax_income=10,
                shares_outstanding=100 + 10 * index,
            )
        )
    return rows


def _fake_dcf(margin=0.30):
    return SimpleNamespace(margin_of_safety=margin, intrinsic_value_per_share=125.0)


def test_no_fundamentals_is_insufficient():
    result = BuffettClassicMethodology().evaluate("TEST", [], _Prices())
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.score is None
    assert result.confidence == Confidence.LOW


def test_bank_is_not_applicable():
    rows = [
        _row(
            2025,
            sector="Financial Services",
            industry="Banks - Diversified",
            revenue=100,
            net_income=10,
            total_assets=1000,
        )
    ]
    result = BuffettClassicMethodology().evaluate("JPM", rows, _Prices())
    assert result.verdict == Verdict.NOT_APPLICABLE
    assert result.score is None
    assert any("financial" in reason.lower() for reason in result.reasons)


def test_strong_company_is_buy(monkeypatch):
    monkeypatch.setattr(
        methodology_module.BuffettClassicMethodology,
        "_dcf",
        staticmethod(lambda *args: _fake_dcf()),
    )
    result = BuffettClassicMethodology().evaluate("TEST", _strong_rows(), _Prices())
    assert result.verdict == Verdict.BUY
    assert result.score == 100.0
    assert result.confidence == Confidence.HIGH
    assert result.failed_rules == []


def test_weak_company_is_avoid(monkeypatch):
    monkeypatch.setattr(
        methodology_module.BuffettClassicMethodology,
        "_dcf",
        staticmethod(lambda *args: _fake_dcf(-0.5)),
    )
    result = BuffettClassicMethodology().evaluate("TEST", _weak_rows(), _Prices())
    assert result.verdict == Verdict.AVOID
    assert result.score is not None and result.score < 50
    assert result.failed_rules


def test_missing_dcf_degrades_to_medium_confidence():
    # The real _dcf catches the missing beta and returns None.
    result = BuffettClassicMethodology().evaluate(
        "TEST", _strong_rows(), _ExplodingPrices()
    )
    assert result.verdict == Verdict.BUY  # 2/24 weight missing is tolerated
    assert result.confidence == Confidence.MEDIUM
    assert result.metrics.get("dcf_margin_of_safety") is None


def test_reasons_are_grouped_by_category():
    result = BuffettClassicMethodology().evaluate("TEST", _weak_rows(), _Prices())
    text = "\n".join(result.reasons)
    for category in (
        "moat",
        "financial_strength",
        "earnings_quality",
        "capital_allocation",
        "valuation",
        "management",
    ):
        assert f"{category}:" in text
    assert "verdict:" in text


def test_rules_expose_the_twenty_checks():
    rules = BuffettClassicMethodology().rules()
    ids = {rule.id for rule in rules}
    assert len(ids) == 20
    assert "buffett.roic_current" in ids
    assert "buffett.dcf_margin_of_safety_20" in ids
    assert "buffett.insider_ownership" in ids


def test_metadata_documents_thresholds_and_limits():
    metadata = BuffettClassicMethodology().metadata()
    assert metadata["version"] == "2.0.0"
    assert metadata["thresholds"]["buy"] == 0.85
    assert metadata["thresholds"]["watch"] == 0.70
    limitations = " ".join(metadata["known_limitations"]).lower()
    assert "maintenance" in limitations
    assert "reit" in limitations
