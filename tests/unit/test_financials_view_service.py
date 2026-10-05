"""FinancialsViewService: classification, formatting, dedupe, demo fixtures."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from backend.services.financials_view_service import (
    DEFAULT_MAX_YEARS,
    FinancialsViewService,
    classify_concept,
    filter_rows,
    format_fact_value,
    humanize_concept,
    table_rows,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financials"


class _Repo:
    def __init__(self, facts, name="Apple Inc."):
        self._facts = list(facts)
        self._name = name
        self.calls: list[tuple] = []

    def list_all_facts(self, ticker, fiscal_period="FY", max_years=None):
        self.calls.append((ticker, fiscal_period, max_years))
        return list(self._facts)

    def get_company_name(self, ticker):
        return self._name


def _facts() -> list[dict]:
    raw = json.loads((FIXTURES / "aapl_facts.json").read_text(encoding="utf-8"))
    return [dict(fact, value=Decimal(str(fact["value"]))) for fact in raw]


def _view(max_years=DEFAULT_MAX_YEARS):
    return FinancialsViewService(_Repo(_facts())).build("AAPL", "FY", max_years)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def test_build_populates_every_bucket():
    view = _view()
    assert view is not None
    assert view.ticker == "AAPL"
    assert view.company_name == "Apple Inc."
    assert view.fiscal_period == "FY"
    assert len(view.balance_sheet) == 15
    assert len(view.income_statement) == 9
    assert len(view.cash_flow) == 4
    assert len(view.other) == 2


def test_repository_receives_the_ticker_period_and_cap():
    repo = _Repo(_facts())
    FinancialsViewService(repo).build("aapl", "FY", 5)
    assert repo.calls == [("AAPL", "FY", 5)]


def test_balance_sheet_holds_only_balance_sheet_concepts():
    view = _view()
    assert view is not None
    for row in view.balance_sheet:
        assert classify_concept(row.concept) == "balance_sheet", row.concept


def test_income_statement_holds_only_income_concepts():
    view = _view()
    assert view is not None
    for row in view.income_statement:
        assert classify_concept(row.concept) == "income_statement", row.concept


def test_cash_flow_holds_only_cash_flow_concepts():
    view = _view()
    assert view is not None
    for row in view.cash_flow:
        assert classify_concept(row.concept) == "cash_flow", row.concept


def test_unmatched_concepts_land_in_other_and_nothing_is_dropped():
    facts = _facts()
    view = _view()
    assert view is not None
    other_concepts = {row.concept for row in view.other}
    assert "EntityPublicFloat" in other_concepts
    assert "EffectiveIncomeTaxRateContinuingOperations" in other_concepts
    assert view.unmatched_count == len(view.other)
    total = (
        len(view.balance_sheet)
        + len(view.income_statement)
        + len(view.cash_flow)
        + len(view.other)
    )
    assert total == len({fact["concept"] for fact in facts})


def test_years_are_sorted_newest_first():
    view = _view()
    assert view is not None
    assert view.years == [2025, 2024, 2023]


def test_values_use_the_statement_convention():
    view = _view()
    assert view is not None
    net_income = next(
        row for row in view.income_statement if row.concept == "NetIncomeLoss"
    )
    assert net_income.values[2025] == "$112,010,000,000"
    assert net_income.values[2023] == "($7,172,000,000)"  # negatives in parentheses
    eps = next(
        row for row in view.income_statement if row.concept == "EarningsPerShareDiluted"
    )
    assert eps.values[2025] == "$7.39"
    assert eps.values[2023] == "($0.45)"
    rate = next(
        row
        for row in view.other
        if row.concept == "EffectiveIncomeTaxRateContinuingOperations"
    )
    assert rate.values[2025] == "0.1543"


def test_dedupe_keeps_the_latest_period_end():
    view = _view()
    assert view is not None
    payable = next(
        row for row in view.balance_sheet if row.concept == "AccountsPayableCurrent"
    )
    # FY2025 carries the comparative 2024-09-28 row too; the own year-end wins.
    assert payable.values[2025] == "$69,860,000,000"


def test_max_years_caps_the_window():
    view = _view(max_years=2)
    assert view is not None
    assert view.years == [2025, 2024]
    # Values outside the window are not rendered.
    assets = next(row for row in view.balance_sheet if row.concept == "Assets")
    assert 2023 not in assets.values


def test_build_with_abbreviate_formats_large_values():
    view = FinancialsViewService(_Repo(_facts())).build(
        "AAPL", "FY", DEFAULT_MAX_YEARS, abbreviate=True
    )
    assert view is not None
    assets = next(row for row in view.balance_sheet if row.concept == "Assets")
    assert assets.values[2025] == "$364.98B"
    # Shares keep the suffix; the default mode still shows full precision.
    shares = next(
        row
        for row in view.balance_sheet
        if row.concept == "EntityCommonStockSharesOutstanding"
    )
    assert shares.values[2025] == "14.78B sh"
    full = next(
        row
        for row in _view().balance_sheet
        if row.concept == "EntityCommonStockSharesOutstanding"
    )
    assert full.values[2025] == "14,776,353,000"


def test_empty_facts_return_none():
    assert FinancialsViewService(_Repo([])).build("AAPL") is None


def test_blank_ticker_returns_none_without_querying():
    repo = _Repo(_facts())
    assert FinancialsViewService(repo).build("  ") is None
    assert repo.calls == []


def test_repository_without_facts_support_returns_none():
    assert FinancialsViewService(object()).build("AAPL") is None


def test_build_is_deterministic():
    assert _view() == _view()


def test_many_facts_add_a_guidance_warning(monkeypatch):
    import backend.services.financials_view_service as module

    monkeypatch.setattr(module, "FACTS_GUIDANCE_THRESHOLD", 5)
    view = _view()
    assert view is not None
    assert view.extraction_warnings
    assert "facts in this window" in view.extraction_warnings[0]


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def test_humanize_curated_and_fallback():
    assert humanize_concept("NetIncomeLoss") == "Net Income"
    assert humanize_concept("SomeWeirdConceptXYZ") == "Some Weird Concept XYZ"
    assert (
        humanize_concept("us-gaap:AssetsHeldInTrustNoncurrent")
        == "Assets Held In Trust Noncurrent"
    )


def test_classify_concept_uses_mappings_then_heuristics():
    # Curated mappings from the repository.
    assert classify_concept("Assets") == "balance_sheet"
    assert classify_concept("Revenues") == "income_statement"
    assert classify_concept("NetCashProvidedByUsedInOperatingActivities") == "cash_flow"
    # Prefix/name heuristics.
    assert classify_concept("AssetsHeldInTrustNoncurrent") == "balance_sheet"
    assert classify_concept("LiabilitiesSubjectToCompromise") == "balance_sheet"
    assert classify_concept("EquityMethodInvestments") == "balance_sheet"
    assert (
        classify_concept("RevenueRemainingPerformanceObligation") == "income_statement"
    )
    assert classify_concept("EarningsPerShareDiluted") == "income_statement"
    assert classify_concept("ComprehensiveIncomeNetOfTax") == "income_statement"
    assert (
        classify_concept("PaymentsToAcquireBusinessesNetOfCashAcquired") == "cash_flow"
    )
    assert classify_concept("ProceedsFromIssuanceOfLongTermDebt") == "cash_flow"
    # Strong families beat the "Asset" contains rule.
    assert classify_concept("PaymentsToAcquireIntangibleAssets") == "cash_flow"
    assert classify_concept("IncreaseDecreaseInOtherOperatingAssets") == "cash_flow"
    assert classify_concept("AmortizationOfIntangibleAssets") == "income_statement"
    assert classify_concept("DeferredTaxAssetsNet") == "balance_sheet"
    assert classify_concept("OtherLiabilitiesNoncurrent") == "balance_sheet"
    # Nothing matches -> other (never dropped).
    assert classify_concept("EntityPublicFloat") == "other"
    assert classify_concept("EffectiveIncomeTaxRateContinuingOperations") == "other"


def test_format_fact_value_units():
    assert format_fact_value(Decimal(29943000000), "USD") == "$29,943,000,000"
    assert format_fact_value(Decimal(-7172000000), "USD") == "($7,172,000,000)"
    assert format_fact_value(Decimal("6.08"), "USD/shares") == "$6.08"
    assert format_fact_value(Decimal(14776353000), "shares") == "14,776,353,000"
    assert format_fact_value(Decimal("0.1543"), "pure") == "0.1543"
    assert format_fact_value(Decimal(0), "USD") == "$0"
    assert format_fact_value(None, "USD") == ""


def test_filter_rows_by_label_concept_and_unit():
    view = _view()
    assert view is not None
    by_label = filter_rows(view.balance_sheet, query="total assets")
    assert [row.concept for row in by_label] == ["Assets"]
    by_concept = filter_rows(view.income_statement, query="NetIncomeLoss")
    assert [row.concept for row in by_concept] == ["NetIncomeLoss"]
    only_usd = filter_rows(view.other, units={"USD"})
    assert [row.concept for row in only_usd] == ["EntityPublicFloat"]
    everything = filter_rows(view.cash_flow)
    assert len(everything) == len(view.cash_flow)


def test_table_rows_columns_and_missing_years():
    view = _view()
    assert view is not None
    rows = table_rows(view.balance_sheet, view.years)
    assets = next(row for row in rows if row["Concept"] == "Assets")
    assert list(assets.keys()) == [
        "Label",
        "FY2025",
        "FY2024",
        "FY2023",
        "Unit",
        "Concept",
    ]
    assert assets["Label"] == "Total Assets"
    assert assets["FY2025"] == "$364,980,000,000"
    obligation = next(
        row
        for row in table_rows(view.income_statement, view.years)
        if row["Concept"] == "RevenueRemainingPerformanceObligation"
    )
    assert obligation["FY2024"] == ""  # a year without a fact renders blank


# ---------------------------------------------------------------------------
# demo fixtures
# ---------------------------------------------------------------------------
def _demo_payload() -> dict:
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "fiscal_period": "FY",
        "years": [2025, 2024],
        "note": "Demo fixture: top concepts, 2 years.",
        "balance_sheet": [
            {
                "concept": "Assets",
                "label": "Total Assets",
                "values": {"2025": "$364,980,000,000", "2024": "$352,583,000,000"},
                "unit": "USD",
            }
        ],
        "income_statement": [],
        "cash_flow": [],
        "other": [],
        "unmatched_count": 0,
    }


def test_demo_fixture_loads(monkeypatch, tmp_path):
    import backend.services.financials_view_service as module

    demo = tmp_path / "financials"
    demo.mkdir()
    (demo / "AAPL.json").write_text(json.dumps(_demo_payload()), encoding="utf-8")
    monkeypatch.setattr(module, "DEMO_ROOT", tmp_path)
    monkeypatch.setenv("VI_DEMO", "1")

    view = FinancialsViewService().build("AAPL")
    assert view is not None
    assert view.years == [2025, 2024]
    assert view.balance_sheet[0].values[2025] == "$364,980,000,000"
    assert view.extraction_warnings == ["Demo fixture: top concepts, 2 years."]


def test_demo_fixture_caps_years(monkeypatch, tmp_path):
    import backend.services.financials_view_service as module

    demo = tmp_path / "financials"
    demo.mkdir()
    (demo / "AAPL.json").write_text(json.dumps(_demo_payload()), encoding="utf-8")
    monkeypatch.setattr(module, "DEMO_ROOT", tmp_path)
    monkeypatch.setenv("VI_DEMO", "1")

    view = FinancialsViewService().build("AAPL", "FY", 1)
    assert view is not None
    assert view.years == [2025]


def test_demo_quarterly_view_returns_none(monkeypatch, tmp_path):
    import backend.services.financials_view_service as module

    demo = tmp_path / "financials"
    demo.mkdir()
    (demo / "AAPL.json").write_text(json.dumps(_demo_payload()), encoding="utf-8")
    monkeypatch.setattr(module, "DEMO_ROOT", tmp_path)
    monkeypatch.setenv("VI_DEMO", "1")

    assert FinancialsViewService().build("AAPL", "Q1") is None
