"""Tests for methodology ranking service."""

from unittest.mock import MagicMock, patch

from backend.methodologies.base import Confidence, MethodologyResult, Verdict
from backend.services.methodology_ranking_service import (
    _get_universe_data,
    rank_by_methodology,
    rank_combined,
)


def _make_result(methodology="graham", verdict=Verdict.BUY, score=85.0, reasons=None):
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
                    "score": 92,
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
                    "score": 89,
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
    assert results[0].score == 92


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

    def side_effect(ticker, rows, price, market_cap, **kwargs):
        if ticker == "AAPL":
            return MethodologiesView(
                ticker="AAPL",
                table=[],
                details=[
                    {
                        "methodology": "graham",
                        "family": "DEEP_VALUE",
                        "verdict": "BUY",
                        "score": 90,
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
                        "score": 75,
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

    def side_effect(ticker, rows, price, market_cap, **kwargs):
        return MethodologiesView(
            ticker="AAPL",
            table=[],
            details=[
                {
                    "methodology": "graham",
                    "family": "DEEP_VALUE",
                    "verdict": "BUY",
                    "score": 90,
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
                    "score": 30,
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

    def side_effect(ticker, rows, price, market_cap, **kwargs):
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
                    "score": 75,
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


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_combined_weighted_with_weights(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    """Weights param changes output ordering vs equal weights."""
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

    def side_effect(ticker, rows, price, market_cap, **kwargs):
        if ticker == "AAPL":
            return MethodologiesView(
                ticker="AAPL",
                table=[],
                details=[
                    {
                        "methodology": "graham",
                        "family": "DEEP_VALUE",
                        "verdict": "BUY",
                        "score": 95,
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
                        "score": 50,
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
        elif ticker == "MSFT":
            return MethodologiesView(
                ticker="MSFT",
                table=[],
                details=[
                    {
                        "methodology": "graham",
                        "family": "DEEP_VALUE",
                        "verdict": "BUY",
                        "score": 60,
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
                        "score": 90,
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

    equal = rank_combined(
        ["graham", "lynch_garp"], ["AAPL", "MSFT"], strategy="weighted", top_n=10
    )
    graham_heavy = rank_combined(
        ["graham", "lynch_garp"],
        ["AAPL", "MSFT"],
        strategy="weighted",
        top_n=10,
        weights={"graham": 3.0, "lynch_garp": 1.0},
    )
    lynch_heavy = rank_combined(
        ["graham", "lynch_garp"],
        ["AAPL", "MSFT"],
        strategy="weighted",
        top_n=10,
        weights={"graham": 1.0, "lynch_garp": 3.0},
    )

    # AAPL has better Graham (9.5 vs 6.0), MSFT better Lynch (9.0 vs 5.0)
    # Equal weights: AAPL=(9.5+5.0)/2=7.25, MSFT=(6.0+9.0)/2=7.5 -> MSFT first
    assert equal[0].ticker == "MSFT"
    # Graham heavy (3:1): AAPL=(9.5*3+5.0)/4=8.375, MSFT=(6.0*3+9.0)/4=6.75 -> AAPL first
    assert graham_heavy[0].ticker == "AAPL"
    # Lynch heavy (1:3): AAPL=(9.5+15.0)/4=6.125, MSFT=(6.0+27.0)/4=8.25 -> MSFT first
    assert lynch_heavy[0].ticker == "MSFT"
    # Weights change ordering vs equal
    assert equal[0].ticker != graham_heavy[0].ticker


@patch("backend.services.price_service.get_price_service")
@patch("backend.app.cli.build_financial_repository")
def test_universe_data_reads_best_available_with_core_merge(
    mock_build_repo, mock_price_service
):
    """The ranking path must use the effective-year/core-aware repository."""
    row = MagicMock()
    repository = mock_build_repo.return_value
    repository.get_best_available.return_value = [row]
    price_service = mock_price_service.return_value
    price_service.get_current_price.return_value = 150.0
    price_service.get_market_cap.return_value = 2e12

    fundamentals, prices, market_caps = _get_universe_data(["AAPL"])

    # 11 rows: the ranking path needs the "10 years ago" row (C2).
    repository.get_best_available.assert_called_once_with("AAPL", max_years=11)
    assert fundamentals["AAPL"] == [row]
    assert prices["AAPL"] == 150.0
    assert market_caps["AAPL"] == 2e12


@patch("backend.services.methodology_ranking_service.run_methodologies")
@patch("backend.services.methodology_ranking_service._get_universe_data")
@patch("backend.services.methodology_ranking_service.registry")
@patch("backend.services.methodology_ranking_service.discover")
def test_rank_by_methodology_applies_demote_only_tiers(
    mock_discover, mock_registry, mock_get_data, mock_run
):
    """Absolute fallback (<50 scored): 95->STRONG, 65->BUY, 55->WEAK; WATCH stays."""
    mock_discover.return_value = None
    mock_method = MagicMock()
    mock_method.family = "DEEP_VALUE"
    mock_registry.get.return_value = mock_method
    tickers = ["STRONG", "NORMAL", "WEAK", "WATCHY"]
    mock_get_data.return_value = (
        {},
        {ticker: 150.0 for ticker in tickers},
        {ticker: 2e12 for ticker in tickers},
    )

    from backend.services.ui_adapter import MethodologiesView

    def view(ticker, verdict, score):
        return MethodologiesView(
            ticker=ticker,
            table=[],
            details=[
                {
                    "methodology": "graham",
                    "family": "DEEP_VALUE",
                    "verdict": verdict,
                    "score": score,
                    "confidence": "HIGH",
                    "reasons": [verdict],
                    "red_flags": [],
                }
            ],
            agreement=True,
            family_lines=[],
            explanation="",
            consensus="",
        )

    mock_run.side_effect = lambda ticker, *args, **kwargs: {
        "STRONG": view("STRONG", "BUY", 95.0),
        "NORMAL": view("NORMAL", "BUY", 65.0),
        "WEAK": view("WEAK", "BUY", 55.0),
        "WATCHY": view("WATCHY", "WATCH", 99.0),
    }[ticker]

    results = {item.ticker: item for item in rank_by_methodology("graham", tickers)}

    assert results["STRONG"].verdict is Verdict.STRONG_BUY
    assert results["STRONG"].tier == "STRONG_BUY"
    assert results["NORMAL"].verdict is Verdict.BUY
    assert results["WEAK"].verdict is Verdict.WEAK_BUY
    # Demote-only: a high score never promotes a WATCH.
    assert results["WATCHY"].verdict is Verdict.WATCH
    assert results["WATCHY"].tier is None
