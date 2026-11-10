"""REIT / bank policy (v0.27.0): classification, badges and scorecard behaviour.

Hermetic: fake fundamentals + fake prices. The policy is:
- REITs are scored by every methodology and carry a visible ``[REIT]`` chip;
- real-estate services firms (CBRE, CSGP) are *not* REITs;
- banks keep the scorecard N/A and carry a ``[BANK]`` chip.
"""

from __future__ import annotations

import json

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Verdict
from backend.methodologies.common.company_type import company_flags, is_reit
from backend.services import cli_output
from backend.services.methodology_ranking_service import RankedTicker
from backend.services.scorecard_service import (
    NA,
    Scorecard,
    ScorecardService,
)
from cli import theme
from cli.commands.rank import _single_dict
from cli.commands.scorecard import _render


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------
def test_is_reit_vici_true():
    assert is_reit("Real Estate", "REIT - Diversified") is True


def test_is_reit_amt_true():
    assert is_reit("Real Estate", "REIT - Specialty") is True


def test_is_reit_cbre_false():
    assert is_reit("Real Estate", "Real Estate Services") is False


def test_is_reit_csgp_false():
    assert is_reit("Real Estate", "Real Estate Services") is False


def test_is_reit_without_industry_falls_back_to_sector():
    assert is_reit("Real Estate", None) is True
    assert is_reit("Technology", None) is False


def test_is_reit_nothing_known_is_false():
    assert is_reit() is False


def test_company_flags_reit_vs_bank():
    reit_row = _row(sector="Real Estate", industry="REIT - Retail")
    bank_row = _row(sector="Financial Services", industry="Banks - Diversified")
    services_row = _row(sector="Real Estate", industry="Real Estate Services")

    assert company_flags(reit_row) == {"reit"}
    assert company_flags(bank_row) == {"bank"}
    assert company_flags(services_row) == set()
    assert company_flags(None) == set()


def test_bank_and_reit_flags_never_collide_in_a_sample():
    known_reits = (
        "VICI",
        "O",
        "AMT",
        "PLD",
        "SPG",
        "EQIX",
        "PSA",
        "WELL",
        "DLR",
        "CCI",
    )
    known_banks = ("JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC")
    reit_rows = [
        _row(sector="Real Estate", industry="REIT - Retail") for _ in known_reits
    ]
    bank_rows = [
        _row(sector="Financial Services", industry="Banks - Diversified")
        for _ in known_banks
    ]

    for row in reit_rows:
        assert company_flags(row) == {"reit"}
    for row in bank_rows:
        assert company_flags(row) == {"bank"}
    assert all(
        not ({"reit", "bank"} <= company_flags(row)) for row in reit_rows + bank_rows
    )


# ---------------------------------------------------------------------------
# scorecard
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
        return 100.0

    def get_market_cap(self, ticker):
        return 1_000.0


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
    }
    data.update(overrides)
    return NormalizedFinancials(**data)


def _history(**overrides):
    return [
        _row(
            2020 + index,
            revenue=100.0 + 10 * index,
            net_income=10.0 + 2 * index,
            stockholders_equity=40.0 + 4 * index,
            **overrides,
        )
        for index in range(6)
    ]


def test_scorecard_reit_scored_not_na():
    card = ScorecardService(
        repository=_FakeRepository(
            _history(sector="Real Estate", industry="REIT - Retail")
        ),
        price_service=_FakePrices(),
    ).build("VICI")

    assert card is not None
    assert card.overall_flags == ("reit",)
    assert all(dimension.verdict != NA for dimension in card.dimensions)
    assert any(dimension.score is not None for dimension in card.dimensions)


def test_scorecard_bank_still_na_with_bank_flag():
    card = ScorecardService(
        repository=_FakeRepository(
            _history(sector="Financial Services", industry="Banks - Diversified")
        ),
        price_service=_FakePrices(),
    ).build("JPM")

    assert card is not None
    assert card.overall_flags == ("bank",)
    assert {dimension.verdict for dimension in card.dimensions} == {NA}
    assert card.overall == NA
    assert any("specialized" in note.lower() for note in card.notes)


def test_scorecard_reit_caption_is_visible():
    card = ScorecardService(
        repository=_FakeRepository(
            _history(sector="Real Estate", industry="REIT - Retail")
        ),
        price_service=_FakePrices(),
    ).build("VICI")

    assert any("FFO" in note for note in card.notes)


def test_json_includes_flags():
    card = ScorecardService(
        repository=_FakeRepository(
            _history(sector="Real Estate", industry="REIT - Retail")
        ),
        price_service=_FakePrices(),
    ).build("VICI")

    payload = json.loads(json.dumps(card.to_dict(), default=str))
    assert payload["overall_flags"] == ["reit"]
    assert all(item["flags"] == ["reit"] for item in payload["methodologies"])


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------
def test_cli_scorecard_shows_reit_badge(capsys):
    cli_output.reset_no_color()
    card = Scorecard(
        ticker="VICI",
        company="VICI Properties",
        sector="Real Estate",
        industry="REIT - Diversified",
        period="FY",
        price=30.0,
        market_cap=30_000.0,
        generated="",
        dimensions=(),
        overall="Mixed",
        disagreements=(),
        methodologies=(),
        data_quality="HIGH",
        notes=(),
        overall_flags=("reit",),
    )
    _render(card)

    assert "[REIT]" in capsys.readouterr().out


def test_cli_bank_badge_is_purple_and_visible():
    cli_output.reset_no_color()
    text = theme.company_badges(("bank",))
    assert "[BANK]" in text


def test_cli_scorecard_shows_bank_badge(capsys):
    cli_output.reset_no_color()
    card = Scorecard(
        ticker="JPM",
        company="JPMorgan Chase",
        sector="Financial Services",
        industry="Banks - Diversified",
        period="FY",
        price=200.0,
        market_cap=600_000.0,
        generated="",
        dimensions=(),
        overall=NA,
        disagreements=(),
        methodologies=(),
        data_quality="HIGH",
        notes=(),
        overall_flags=("bank",),
    )
    _render(card)

    assert "[BANK]" in capsys.readouterr().out


def test_rank_shows_reit_flag_in_json_and_row():
    item = RankedTicker(
        ticker="VICI",
        verdict=Verdict.WATCH,
        score=84.21,
        family="DEEP_VALUE",
        n_a_reason=None,
        flags=("reit",),
    )
    assert _single_dict(item)["flags"] == ["reit"]
    assert "[REIT]" in theme.company_badges(item.flags)
