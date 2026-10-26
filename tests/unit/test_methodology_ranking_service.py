"""Tests for methodology ranking service."""

from unittest.mock import MagicMock, patch

from backend.methodologies.base import Confidence, MethodologyResult, Verdict
from backend.services.methodology_ranking_service import (
    rank_by_methodology,
    rank_combined,
)


def _make_result(methodology="graham", verdict=Verdict.BUY, score=8.5, reasons=None):
    return MethodologyResult(
        methodology=methodology,
        version="1.0.0",
        family="DEEP_VALUE",
        verdict=verdict,
        score=score,
        metrics={},
        reasons=reasons or [f"{verdict.value} based on rules"],
        red_flags=[],
        confidence=Confidence.HIGH,
        sources=[],
    )


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_by_methodology_returns_top_n(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    mock_get_data.return_value = (
        {},
        {"AAPL": 150.0, "MSFT": 300.0},
        {"AAPL": 2e12, "MSFT": 2.2e12},
    )

    from backend.services.ui_adapter import MethodologiesView

    mock_run.side_effect = [
        MethodologiesView(
            ticker="AAPL",
            table=[],
            details=[
                {
                    "methodology": "graham",
                    "family": "DEEP_VALUE",
                    "verdict": "BUY",
                    "score": 9.2,
                    "confidence": "HIGH",
                    "category": None,
                    "category_short": None,
                    "rule_outcomes": {},
                    "metrics": {},
                    "reasons": ["BUY"],
                    "red_flags": [],
                }
            ],
            agreement=True,
            family_lines=[],
            explanation="",
            consensus="",
        ),
        MethodologiesView(
            ticker="MSFT",
            table=[],
            details=[
                {
                    "methodology": "graham",
                    "family": "DEEP_VALUE",
                    "verdict": "BUY",
                    "score": 8.9,
                    "confidence": "HIGH",
                    "category": None,
                    "category_short": None,
                    "rule_outcomes": {},
                    "metrics": {},
                    "reasons": ["BUY"],
                    "red_flags": [],
                }
            ],
            agreement=True,
            family_lines=[],
            explanation="",
            consensus="",
        ),
    ]

    results = rank_by_methodology("graham", ["AAPL", "MSFT"], top_n=1)
    assert len(results) == 1
    assert results[0].ticker == "AAPL"
    assert results[0].score == 9.2


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_by_methodology_excludes_na(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    mock_get_data.return_value = ({}, {"JPM": 150.0}, {"JPM": 500e9})

    from backend.services.ui_adapter import MethodologiesView

    mock_run.return_value = MethodologiesView(
        ticker="JPM",
        table=[],
        details=[
            {
                "methodology": "graham",
                "family": "DEEP_VALUE",
                "verdict": "N/A",
                "score": None,
                "confidence": "HIGH",
                "category": None,
                "category_short": None,
                "rule_outcomes": {},
                "metrics": {},
                "reasons": ["financial company"],
                "red_flags": [],
            }
        ],
        agreement=True,
        family_lines=[],
        explanation="",
        consensus="",
    )

    results = rank_by_methodology("graham", ["JPM"], top_n=20, include_na=False)
    assert len(results) == 0


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_by_methodology_includes_na(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    mock_get_data.return_value = ({}, {"JPM": 150.0}, {"JPM": 500e9})

    from backend.services.ui_adapter import MethodologiesView

    mock_run.return_value = MethodologiesView(
        ticker="JPM",
        table=[],
        details=[
            {
                "methodology": "graham",
                "family": "DEEP_VALUE",
                "verdict": "N/A",
                "score": None,
                "confidence": "HIGH",
                "category": None,
                "category_short": None,
                "rule_outcomes": {},
                "metrics": {},
                "reasons": ["financial company"],
                "red_flags": [],
            }
        ],
        agreement=True,
        family_lines=[],
        explanation="",
        consensus="",
    )

    results = rank_by_methodology("graham", ["JPM"], top_n=20, include_na=True)
    assert len(results) == 1
    assert results[0].n_a_reason is not None


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_combined_and_requires_buy_or_watch(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    mock_get_data.return_value = ({}, {"AAPL": 150.0}, {"AAPL": 2e12})

    from backend.services.ui_adapter import MethodologiesView

    def side_effect(ticker, rows, price, market_cap):
        if ticker == "AAPL":
            return MethodologiesView(
                ticker="AAPL",
                table=[],
                details=[
                    {
                        "methodology": "graham",
                        "family": "DEEP_VALUE",
                        "verdict": "BUY",
                        "score": 9.0,
                        "confidence": "HIGH",
                        "category": None,
                        "category_short": None,
                        "rule_outcomes": {},
                        "metrics": {},
                        "reasons": ["BUY"],
                        "red_flags": [],
                    },
                    {
                        "methodology": "lynch_garp",
                        "family": "GARP",
                        "verdict": "WATCH",
                        "score": 7.5,
                        "confidence": "HIGH",
                        "category": None,
                        "category_short": None,
                        "rule_outcomes": {},
                        "metrics": {},
                        "reasons": ["WATCH"],
                        "red_flags": [],
                    },
                ],
                agreement=False,
                family_lines=[],
                explanation="",
                consensus="",
            )
        return MethodologiesView(
            ticker=ticker,
            table=[],
            details=[],
            agreement=True,
            family_lines=[],
            explanation="",
            consensus="",
        )

    mock_run.side_effect = side_effect
    results = rank_combined(["graham", "lynch_garp"], ["AAPL"], strategy="and")
    assert len(results) == 1


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_combined_or_includes_any(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    mock_get_data.return_value = ({}, {"AAPL": 150.0}, {"AAPL": 2e12})

    from backend.services.ui_adapter import MethodologiesView

    def side_effect(ticker, rows, price, market_cap):
        return MethodologiesView(
            ticker="AAPL",
            table=[],
            details=[
                {
                    "methodology": "graham",
                    "family": "DEEP_VALUE",
                    "verdict": "BUY",
                    "score": 9.0,
                    "confidence": "HIGH",
                    "category": None,
                    "category_short": None,
                    "rule_outcomes": {},
                    "metrics": {},
                    "reasons": ["BUY"],
                    "red_flags": [],
                },
                {
                    "methodology": "lynch_garp",
                    "family": "GARP",
                    "verdict": "AVOID",
                    "score": 3.0,
                    "confidence": "HIGH",
                    "category": None,
                    "category_short": None,
                    "rule_outcomes": {},
                    "metrics": {},
                    "reasons": ["AVOID"],
                    "red_flags": [],
                },
            ],
            agreement=False,
            family_lines=[],
            explanation="",
            consensus="",
        )

    mock_run.side_effect = side_effect
    results = rank_combined(["graham", "lynch_garp"], ["AAPL"], strategy="or")
    assert len(results) == 1


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_combined_weighted_requires_numeric_scores(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    mock_get_data.return_value = ({}, {"AAPL": 150.0}, {"AAPL": 2e12})

    from backend.services.ui_adapter import MethodologiesView

    def side_effect(ticker, rows, price, market_cap):
        return MethodologiesView(
            ticker="AAPL",
            table=[],
            details=[
                {
                    "methodology": "graham",
                    "family": "DEEP_VALUE",
                    "verdict": "BUY",
                    "score": None,
                    "confidence": "HIGH",
                    "category": None,
                    "category_short": None,
                    "rule_outcomes": {},
                    "metrics": {},
                    "reasons": ["BUY"],
                    "red_flags": [],
                },
                {
                    "methodology": "lynch_garp",
                    "family": "GARP",
                    "verdict": "BUY",
                    "score": 7.5,
                    "confidence": "HIGH",
                    "category": None,
                    "category_short": None,
                    "rule_outcomes": {},
                    "metrics": {},
                    "reasons": ["BUY"],
                    "red_flags": [],
                },
            ],
            agreement=False,
            family_lines=[],
            explanation="",
            consensus="",
        )

    mock_run.side_effect = side_effect
    results = rank_combined(["graham", "lynch_garp"], ["AAPL"], strategy="weighted")
    assert len(results) == 0
