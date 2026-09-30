"""Marks' measurable rules: cycle, resilience, value and quality."""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Verdict
from backend.methodologies.marks.methodology import MarksMethodology
from backend.methodologies.marks.rules import ALL_RULES


class _Prices:
    def __init__(self, market_cap=2_000.0):
        self._market_cap = market_cap

    def get_market_cap(self, ticker):
        return self._market_cap


class _Boom:
    def get_market_cap(self, ticker):
        raise RuntimeError("yahoo down")


def _row(
    year: int,
    operating_income: float = 150.0,
    ebit: float = 150.0,
    total_debt: float = 400.0,
    stockholders_equity: float = 600.0,
    sector: str | None = None,
) -> NormalizedFinancials:
    return NormalizedFinancials(
        ticker="TEST",
        fiscal_year=year,
        period="FY",
        revenue=1_000.0,
        operating_income=operating_income,
        ebit=ebit,
        ebitda=200.0,
        net_income=100.0,
        interest_expense=20.0,
        total_debt=total_debt,
        stockholders_equity=stockholders_equity,
        cash_and_equivalents=100.0,
        operating_cash_flow=180.0,
        capital_expenditure=50.0,
        sector=sector,
    )


def _healthy_history(**latest_overrides) -> list[NormalizedFinancials]:
    """Five flat, healthy years; overrides apply to the latest year only."""
    rows = [_row(2025, **latest_overrides)]
    rows.extend(_row(year) for year in range(2024, 2019, -1))
    return rows


def _evaluate(rows, prices=None):
    return MarksMethodology().evaluate("TEST", rows, prices or _Prices())


def test_buy_when_all_rules_pass():
    result = _evaluate(_healthy_history())
    assert result.verdict is Verdict.BUY
    assert result.score == 100.0
    assert result.metrics["cycle_position"] == "mid"
    assert set(result.passed_rules) == {rule.id for rule in ALL_RULES}
    assert result.failed_rules == []


def test_peak_cycle_blocks_buy():
    # Latest year far above its own trend: mean-reversion risk.
    result = _evaluate(_healthy_history(operating_income=300.0, ebit=300.0))
    assert result.metrics["cycle_position"] == "peak"
    assert result.verdict is Verdict.WATCH
    assert any("mean reversion" in flag for flag in result.red_flags)
    assert "marks.rule_1_cycle_position" in result.failed_rules


def test_trough_cycle_adds_points_and_still_buys():
    result = _evaluate(_healthy_history(operating_income=90.0, ebit=90.0))
    assert result.metrics["cycle_position"] == "trough"
    assert result.verdict is Verdict.BUY
    assert result.score == 100.0  # 100 + 10, clamped


def test_high_leverage_is_an_automatic_avoid():
    # A known non-financial sector keeps the balance-sheet fingerprint from
    # typing the fixture as financial (same rule as the Ford fix).
    result = _evaluate(_healthy_history(total_debt=1_200.0, sector="Industrials"))
    assert result.verdict is Verdict.AVOID
    assert result.metrics["net_debt_to_ebitda"] > 4.0
    assert any("balance sheet is the risk" in flag for flag in result.red_flags)


def test_weak_roic_fails_quality():
    # Low returns on capital across every year: the 5y average is below 10%.
    rows = [
        _row(year, stockholders_equity=3_000.0, sector="Industrials")
        for year in range(2025, 2019, -1)
    ]
    result = _evaluate(rows)
    assert "marks.rule_4_quality_persistence" in result.failed_rules
    assert result.verdict is Verdict.WATCH


def test_expensive_price_fails_margin_of_safety():
    result = _evaluate(_healthy_history(), prices=_Prices(market_cap=20_000.0))
    assert "marks.rule_3_margin_of_safety" in result.failed_rules
    assert result.verdict is Verdict.WATCH


def test_missing_market_cap_degrades_to_medium_confidence():
    result = _evaluate(_healthy_history(), prices=_Prices(market_cap=None))
    assert "marks.rule_3_margin_of_safety" in result.failed_rules
    assert result.confidence.value == "MEDIUM"


def test_price_service_failure_is_not_an_error():
    result = _evaluate(_healthy_history(), prices=_Boom())
    assert result.verdict is Verdict.WATCH
    assert result.confidence.value == "MEDIUM"


def test_insufficient_history_abstains():
    rows = [_row(2025), _row(2024)]
    result = _evaluate(rows)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("at least 3" in reason for reason in result.reasons)


def test_financial_company_abstains():
    rows = _healthy_history(sector="Financial Services")
    result = _evaluate(rows)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert result.metrics["financial_company"] is True


def test_deterministic_and_sources_cite_the_book():
    first = _evaluate(_healthy_history())
    second = _evaluate(_healthy_history())
    assert first.verdict == second.verdict
    assert first.score == second.score
    assert first.metrics == second.metrics
    assert all("Most Important Thing" in ref.book for ref in first.sources)


def test_metadata_and_rules():
    methodology = MarksMethodology()
    assert len(methodology.rules()) == 4
    metadata = methodology.metadata()
    assert metadata["family"] == "CYCLE_AWARE_VALUE"
    assert any("qualitative subset" in item for item in metadata["known_limitations"])
