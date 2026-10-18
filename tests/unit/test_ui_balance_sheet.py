"""T-format balance sheet: model, mapping coverage and format helpers.

Synthetic payloads are fully consistent (parts sum to the reported
subtotals; total assets == liabilities + equity) so the assertions pin the
paint-vs-compute rules and the balance chip independently of demo data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.repositories.fdb_concept_mapping import BALANCE_SHEET_CONCEPTS
from ui.balance_map import (
    BALANCE_MAP,
    CONTRA_CONCEPTS,
    MASS_SUBTOTAL_CONCEPTS,
    MEMORANDUM_CONCEPTS,
    TOTAL_CONCEPTS,
    mapped_concepts,
)
from ui.balance_sheet import (
    build_balance_model,
    numeric_from_view,
    parse_display_value,
)
from ui.theme.format import DASH, fmt_delta, fmt_money, fmt_multiple, fmt_pct
from ui.theme.labels import FIELD_LABELS, label

REPO = Path(__file__).resolve().parents[2]
DEMO_FINANCIALS = REPO / "data" / "demo" / "financials"
YEAR, PRIOR_YEAR = 2025, 2024


def _units(**override: str) -> dict[str, str]:
    units = {
        "CashAndCashEquivalentsAtCarryingValue": "USD",
        "OtherAssetsCurrent": "USD",
        "AssetsCurrent": "USD",
        "PropertyPlantAndEquipmentNet": "USD",
        "AccountsPayableCurrent": "USD",
        "OtherLiabilitiesCurrent": "USD",
        "LiabilitiesCurrent": "USD",
        "LongTermDebtNoncurrent": "USD",
        "RetainedEarningsAccumulatedDeficit": "USD",
        "StockholdersEquity": "USD",
        "Assets": "USD",
        "Liabilities": "USD",
    }
    units.update(override)
    return units


def _complete_numeric() -> dict[str, dict[int, float]]:
    """A synthetic, fully consistent balance: 150 == 100 + 50."""
    return {
        # current assets: parts sum to the reported subtotal (80 + 20 = 100)
        "CashAndCashEquivalentsAtCarryingValue": {YEAR: 80.0, PRIOR_YEAR: 70.0},
        "OtherAssetsCurrent": {YEAR: 20.0, PRIOR_YEAR: 25.0},
        "AssetsCurrent": {YEAR: 100.0, PRIOR_YEAR: 95.0},
        # non-current: no reported subtotal -> computed from the single line
        "PropertyPlantAndEquipmentNet": {YEAR: 50.0, PRIOR_YEAR: 45.0},
        # current liabilities: parts sum to the reported subtotal (30 + 30)
        "AccountsPayableCurrent": {YEAR: 30.0, PRIOR_YEAR: 28.0},
        "OtherLiabilitiesCurrent": {YEAR: 30.0, PRIOR_YEAR: 32.0},
        "LiabilitiesCurrent": {YEAR: 60.0, PRIOR_YEAR: 60.0},
        # non-current: computed (40)
        "LongTermDebtNoncurrent": {YEAR: 40.0, PRIOR_YEAR: 45.0},
        # equity: line sums to the reported subtotal (50)
        "RetainedEarningsAccumulatedDeficit": {YEAR: 50.0, PRIOR_YEAR: 35.0},
        "StockholdersEquity": {YEAR: 50.0, PRIOR_YEAR: 35.0},
        # totals
        "Assets": {YEAR: 150.0, PRIOR_YEAR: 140.0},
        "Liabilities": {YEAR: 100.0, PRIOR_YEAR: 105.0},
    }


def _masses(model):
    return {mass.key: mass for mass in model.masses}


# ---------------------------------------------------------------------------
# Paint vs compute + balance identity
# ---------------------------------------------------------------------------


def test_balance_sheet_sums_match_backend():
    """Reported subtotals are painted as-is; parts sum exactly to them."""
    model = build_balance_model(_complete_numeric(), _units(), YEAR, [PRIOR_YEAR, YEAR])
    masses = _masses(model)

    for key in ("assets_current", "liab_current", "equity"):
        mass = masses[key]
        assert mass.subtotal_reported is True, key
        assert sum(line.value for line in mass.lines) == pytest.approx(mass.subtotal)

    # No reported subtotal on the non-current masses -> computed from lines.
    for key in ("assets_noncurrent", "liab_noncurrent"):
        mass = masses[key]
        assert mass.subtotal_reported is False, key
        assert mass.subtotal == pytest.approx(sum(line.value for line in mass.lines))

    assert model.total_assets == pytest.approx(150.0)
    assert model.total_assets_reported is True
    assert model.total_liabilities == pytest.approx(100.0)
    assert model.total_liabilities_reported is True
    assert model.total_equity == pytest.approx(50.0)
    assert model.total_equity_reported is True
    assert model.partial is False


def test_balance_sheet_computed_totals_when_unreported():
    """Without ``Assets``/``Liabilities`` tags the totals are summed, flagged."""
    numeric = _complete_numeric()
    numeric.pop("Assets")
    numeric.pop("Liabilities")
    model = build_balance_model(numeric, _units(), YEAR, [PRIOR_YEAR, YEAR])

    assert model.total_assets == pytest.approx(150.0)
    assert model.total_assets_reported is False
    assert model.total_liabilities == pytest.approx(100.0)
    assert model.total_liabilities_reported is False
    assert model.balanced is True
    assert model.delta == pytest.approx(0.0)


def test_balance_sheet_balances():
    model = build_balance_model(_complete_numeric(), _units(), YEAR, [PRIOR_YEAR, YEAR])
    assert model.balanced is True
    assert model.delta == pytest.approx(0.0)


def test_balance_sheet_reports_imbalance_with_delta():
    numeric = _complete_numeric()
    numeric["Assets"] = {YEAR: 160.0}  # 160 - 100 - 70 = +10, over tolerance
    model = build_balance_model(numeric, _units(), YEAR, [PRIOR_YEAR, YEAR])

    assert model.balanced is False
    assert model.delta == pytest.approx(10.0)


def test_balance_sheet_rounding_tolerance_accepts_demo_precision():
    """Demo values are pre-abbreviated ("$35.93B"): sub-cent drift still cuadra."""
    numeric = _complete_numeric()
    numeric["Assets"] = {YEAR: 150.01}  # 0.007% off, inside the 1% tolerance
    model = build_balance_model(numeric, _units(), YEAR, [PRIOR_YEAR, YEAR])
    assert model.balanced is True


def test_balance_sheet_partial_when_totals_missing():
    numeric = _complete_numeric()
    numeric.pop("Assets")
    numeric.pop("Liabilities")
    numeric.pop("StockholdersEquity")
    numeric.pop("RetainedEarningsAccumulatedDeficit")
    model = build_balance_model(numeric, _units(), YEAR, [PRIOR_YEAR, YEAR])

    assert model.balanced is None  # cannot evaluate -> "Cuadre parcial" chip
    assert model.partial is True


def test_balance_sheet_missing_line_renders_none_and_flags_partial():
    """A line present last year but absent now is None (dash), not 0."""
    numeric = _complete_numeric()
    numeric["OtherAssetsCurrent"] = {PRIOR_YEAR: 25.0}
    model = build_balance_model(numeric, _units(), YEAR, [PRIOR_YEAR, YEAR])

    line = next(
        ln for ln in _masses(model)["assets_current"].lines if ln.concept == "OtherAssetsCurrent"
    )
    assert line.value is None
    assert model.partial is True


def test_balance_sheet_contra_asset_negates():
    """Accumulated depreciation is filed positive but must sum as negative."""
    numeric = {
        "PropertyPlantAndEquipmentGross": {YEAR: 100.0},
        "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": {
            YEAR: 40.0
        },
    }
    units = {
        "PropertyPlantAndEquipmentGross": "USD",
        "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": "USD",
    }
    model = build_balance_model(numeric, units, YEAR, [YEAR])
    mass = _masses(model)["assets_noncurrent"]

    values = [line.value for line in mass.lines]
    assert 100.0 in values and -40.0 in values
    assert mass.subtotal == pytest.approx(60.0)


def test_balance_sheet_alias_slot_is_never_double_counted():
    numeric = {
        "CashAndCashEquivalentsAtCarryingValue": {YEAR: 10.0},
        "CashAndCashEquivalents": {YEAR: 99.0},
        "AssetsCurrent": {YEAR: 10.0},
    }
    units = {
        "CashAndCashEquivalentsAtCarryingValue": "USD",
        "CashAndCashEquivalents": "USD",
        "AssetsCurrent": "USD",
    }
    model = build_balance_model(numeric, units, YEAR, [YEAR])
    cash_lines = [
        line
        for line in _masses(model)["assets_current"].lines
        if line.concept.startswith("Cash")
    ]
    assert len(cash_lines) == 1
    assert cash_lines[0].value == 10.0  # first alias in slot order wins


def test_balance_sheet_yoy_carries_prior_year_value():
    model = build_balance_model(_complete_numeric(), _units(), YEAR, [PRIOR_YEAR, YEAR])
    cash = next(
        ln
        for ln in _masses(model)["assets_current"].lines
        if ln.concept == "CashAndCashEquivalentsAtCarryingValue"
    )
    assert cash.value == 80.0
    assert cash.prev_value == 70.0


# ---------------------------------------------------------------------------
# Mapping coverage (schema -> BALANCE_MAP)
# ---------------------------------------------------------------------------


def _allowed_concepts() -> set[str]:
    return (
        mapped_concepts()
        | {c for cs in TOTAL_CONCEPTS.values() for c in cs}
        | {c for cs in MASS_SUBTOTAL_CONCEPTS.values() for c in cs}
        | MEMORANDUM_CONCEPTS
        | CONTRA_CONCEPTS
    )


def test_balance_map_covers_all_fields():
    """Every real-schema balance concept is placeable: no orphans."""
    allowed = _allowed_concepts()
    backend = set(BALANCE_SHEET_CONCEPTS)
    missing = backend - allowed
    assert not missing, f"backend balance concepts without a T slot: {sorted(missing)}"

    fixtures: set[str] = set()
    for path in sorted(DEMO_FINANCIALS.glob("*.json")):
        if path.name.endswith(("_alerts.json", "_insights.json")):
            continue
        payload = json.loads(path.read_text())
        fixtures |= {row["concept"] for row in payload.get("balance_sheet", [])}
    missing_fixtures = fixtures - allowed
    assert not missing_fixtures, f"demo fixture concepts without a T slot: {sorted(missing_fixtures)}"


def test_balance_map_has_no_concept_in_two_slots():
    seen: dict[str, tuple[str, int]] = {}
    for mass, slots in BALANCE_MAP.items():
        for index, slot in enumerate(slots):
            for concept in slot:
                assert concept not in seen, (
                    f"{concept} mapped twice: {seen[concept]} and {(mass, index)}"
                )
                seen[concept] = (mass, index)


def test_balance_map_keeps_memoranda_out_of_the_masses():
    assert not (mapped_concepts() & MEMORANDUM_CONCEPTS)
    # Totals/subtotals are resolved separately and must not appear as lines.
    assert not mapped_concepts() & {
        c for cs in TOTAL_CONCEPTS.values() for c in cs
    }
    assert not mapped_concepts() & {
        c for cs in MASS_SUBTOTAL_CONCEPTS.values() for c in cs
    }


def test_labels_completeness():
    """Every concept the T-view can render has an ES and EN label."""
    required = (
        mapped_concepts()
        | {c for cs in TOTAL_CONCEPTS.values() for c in cs}
        | {c for cs in MASS_SUBTOTAL_CONCEPTS.values() for c in cs}
        | MEMORANDUM_CONCEPTS
    )
    for concept in sorted(required):
        entry = FIELD_LABELS.get(concept)
        assert entry, f"no label for {concept}"
        assert entry.get("es"), f"no ES label for {concept}"
        assert entry.get("en"), f"no EN label for {concept}"


def test_label_never_returns_the_technical_name():
    assert label("CashAndCashEquivalentsAtCarryingValue") == "Efectivo y equivalentes"
    assert label("UnknownConceptXYZ") != "UnknownConceptXYZ"  # humanized fallback


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def test_fmt_money_edge_cases():
    assert fmt_money(None) == DASH
    assert fmt_money(0) == "$0"
    assert fmt_money(35.93e9) == "$35,930,000,000"
    assert fmt_money(35.93e9, scale="B") == "$35.93B"
    assert fmt_money(-1_234.5) == "($1,234.50)"
    assert fmt_money(-1_234_500, scale="k") == "($1,234.50k)"
    assert fmt_money(123_456_789, scale="M") == "$123.46M"


def test_fmt_money_respects_currency_code():
    assert fmt_money(1_000, "EUR") == "€1,000"
    assert fmt_money(1_000, "") == "1,000"


def test_fmt_pct_edge_cases():
    assert fmt_pct(None) == DASH
    assert fmt_pct(0) == "0.0%"
    assert fmt_pct(0.0678) == "6.8%"
    assert fmt_pct(-0.1234) == "-12.3%"


def test_fmt_delta_edge_cases():
    assert fmt_delta(None) == DASH
    assert fmt_delta(0) == "$0"
    assert fmt_delta(5e8, scale="B") == "+$0.50B"
    assert fmt_delta(-2.5e6, scale="M") == "($2.50M)"
    assert fmt_delta(150_000) == "+$150,000"


def test_fmt_multiple_edge_cases():
    assert fmt_multiple(None) == DASH
    assert fmt_multiple(0) == "0.00x"
    assert fmt_multiple(15.5) == "15.50x"
    assert fmt_multiple(-2.75) == "-2.75x"


# ---------------------------------------------------------------------------
# Demo-mode numeric parsing
# ---------------------------------------------------------------------------


def test_parse_display_value_cases():
    assert parse_display_value(None) is None
    assert parse_display_value("") is None
    assert parse_display_value(DASH) is None
    assert parse_display_value("$35.93B") == pytest.approx(35.93e9)
    assert parse_display_value("($1.24M)") == pytest.approx(-1.24e6)
    assert parse_display_value("14.77B sh") == pytest.approx(14.77e9)
    assert parse_display_value("12,345") == pytest.approx(12_345)
    assert parse_display_value("$0") == 0.0
    assert parse_display_value("0.15", "pure") == pytest.approx(0.15)
    assert parse_display_value("not a number") is None


def test_numeric_from_view_parses_demo_fixture(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.services.financials_view_service import FinancialsViewService

    view = FinancialsViewService().build("AAPL", "FY", 3)
    numeric, units = numeric_from_view(view)

    assert units["CashAndCashEquivalentsAtCarryingValue"] == "USD"
    cash = numeric["CashAndCashEquivalentsAtCarryingValue"]
    assert cash and all(value > 0 for value in cash.values())
    model = build_balance_model(numeric, units, max(view.years), list(view.years))
    assert model.total_assets is not None
    assert model.total_assets > 0
    # The un-extended fixture lacks equity/debt detail: the chip may report
    # an imbalance until the demo fixture is completed (Fase 2 asserts True).
