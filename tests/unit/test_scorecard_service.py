"""Phase 1 unit tests for the scorecard domain and service.

The scorecard is an aggregation layer: it adds no financial model of its own.
These tests pin the two things that *are* new — the per-dimension score formula
(``PASS=2 / WATCH=1 / FAIL=0``, with ``INSUFFICIENT`` dropped) and the
``INSUFFICIENT`` degradation rule — plus the deterministic, read-only building
behaviour of :class:`ScorecardService`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.services.financial_insights_service import InsightsReport, MetricInsight
from backend.services.peer_stats_service import PeerStatsService
from backend.services.scorecard_service import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    DIMENSION_ORDER,
    FAIL,
    INSUFFICIENT,
    PASS,
    WATCH,
    DimensionRule,
    DimensionScore,
    ScorecardService,
    _Alerts,
    _attach_peers,
    _build_dimension,
    _confidence_for,
    _disagreements,
    _financial_health_rules,
    _growth_rules,
    _join_names,
    _management_moat_rules,
    _Metrics,
    _overall,
    _shareholder_returns_rules,
    _short_theme,
    _valuation_rules,
    score_rules,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def rule(status: str, rule_id: str = "r") -> DimensionRule:
    return DimensionRule(
        rule_id=rule_id,
        label="Label",
        status=status,
        value="value",
        threshold="threshold",
        reason="reason",
    )


def metric(
    name: str,
    *,
    series: dict[int, float] | None = None,
    cagr_5y: float | None = None,
    trend: str = "stable",
    stability: str = "stable",
    kind: str = "currency",
) -> MetricInsight:
    return MetricInsight(
        metric=name,
        label=name,
        latest_value="—",
        latest_year=None,
        yoy_change_pct=None,
        cagr_5y=cagr_5y,
        cagr_10y=None,
        average_5y=None,
        trend=trend,
        stability=stability,
        direction_changed=False,
        notes=[],
        kind=kind,
        series=series or {},
    )


def metrics(*items: MetricInsight) -> _Metrics:
    return _Metrics(
        InsightsReport(ticker="T", company_name="Test", metrics=list(items))
    )


def dim(key: str, label: str, score: int | None) -> DimensionScore:
    return DimensionScore(
        key=key,
        label=label,
        question="q",
        score=score,
        verdict="Strong" if score is not None else "Insufficient",
        confidence="HIGH",
        evaluable_rules=3 if score is not None else 0,
        rules=(),
        trend="stable",
        summary="",
    )


def alerts(*fired: str, evaluated: int = 5) -> _Alerts:
    report = SimpleNamespace(
        rules_evaluated=evaluated,
        alerts=[SimpleNamespace(rule_id=name) for name in fired],
    )
    return _Alerts(report)


def _row(year: int = 2024, **overrides: float) -> NormalizedFinancials:
    data: dict[str, float | str | int] = {
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


# ---------------------------------------------------------------------------
# score formula
# ---------------------------------------------------------------------------
def test_all_pass_scores_ten():
    score, verdict, evaluable = score_rules([rule(PASS), rule(PASS), rule(PASS)])
    assert score == 10
    assert verdict == "Strong"
    assert evaluable == 3


def test_weighting_is_pass_two_watch_one_fail_zero():
    # PASS(2) + WATCH(1) + FAIL(0) = 3 of a possible 6 -> 10 * 3 / 6 = 5.
    score, verdict, evaluable = score_rules([rule(PASS), rule(WATCH), rule(FAIL)])
    assert score == 5
    assert verdict == "Mixed"
    assert evaluable == 3


def test_insufficient_rules_are_dropped_from_the_denominator():
    rules = [rule(PASS), rule(PASS)] + [rule(INSUFFICIENT)] * 3
    score, _verdict, evaluable = score_rules(rules)
    assert score == 10
    assert evaluable == 2


def test_fewer_than_two_evaluable_rules_is_insufficient_never_zero():
    score, verdict, evaluable = score_rules(
        [rule(PASS), rule(INSUFFICIENT), rule(INSUFFICIENT)]
    )
    assert score is None
    assert verdict == "Insufficient"
    assert evaluable == 1


def test_all_insufficient_is_insufficient():
    score, verdict, evaluable = score_rules([rule(INSUFFICIENT)] * 7)
    assert score is None
    assert verdict == "Insufficient"
    assert evaluable == 0


def test_verdict_bands():
    assert score_rules([rule(FAIL)] * 5)[1] == "Weak"  # 0
    assert score_rules([rule(PASS)] * 4 + [rule(FAIL)])[1] == "Strong"  # 8
    assert score_rules([rule(PASS)] * 3 + [rule(FAIL)] * 2)[1] == "Mixed"  # 6


# ---------------------------------------------------------------------------
# per-dimension confidence
# ---------------------------------------------------------------------------
def test_confidence_high_with_every_rule_evaluated():
    assert _confidence_for([rule(PASS), rule(FAIL), rule(WATCH)]) == CONFIDENCE_HIGH


def test_confidence_medium_with_one_skipped_rule():
    assert _confidence_for([rule(PASS), rule(INSUFFICIENT)]) == CONFIDENCE_MEDIUM


def test_confidence_low_with_two_or_more_skipped_rules():
    assert _confidence_for([rule(PASS), rule(INSUFFICIENT)] * 2) == CONFIDENCE_LOW


def test_build_dimension_sets_confidence():
    strong = _build_dimension("growth", [rule(PASS), rule(PASS)])
    assert strong.confidence == CONFIDENCE_HIGH
    partial = _build_dimension("growth", [rule(PASS), rule(INSUFFICIENT)] * 2)
    assert partial.confidence == CONFIDENCE_LOW


# ---------------------------------------------------------------------------
# per-rule degradation
# ---------------------------------------------------------------------------
def test_growth_rules_pass_on_strong_growth():
    m = metrics(
        metric("revenue", series={2024: 200.0}, cagr_5y=15.0, trend="growing"),
        metric("eps_diluted", cagr_5y=12.0),
        metric("free_cash_flow", cagr_5y=9.0),
    )
    rules = {r.rule_id: r for r in _growth_rules(m, alerts())}
    assert rules["revenue_cagr_5y"].status == PASS
    assert rules["eps_cagr_5y"].status == PASS
    assert rules["fcf_cagr_5y"].status == PASS
    assert rules["revenue_trend"].status == PASS
    assert rules["revenue_decline_alert"].status == PASS


def test_growth_rules_degrade_to_insufficient_without_data():
    rules = _growth_rules(metrics(), alerts(evaluated=0))
    assert all(r.status == INSUFFICIENT for r in rules)


def test_growth_cagr_bands():
    m = metrics(
        metric("revenue", series={2024: 1.0}, cagr_5y=5.0),
        metric("eps_diluted", cagr_5y=2.0),
        metric("free_cash_flow", cagr_5y=-5.0),
    )
    rules = {r.rule_id: r for r in _growth_rules(m, alerts())}
    assert rules["revenue_cagr_5y"].status == WATCH
    assert rules["eps_cagr_5y"].status == FAIL
    assert rules["fcf_cagr_5y"].status == FAIL


def test_financial_health_current_ratio_always_insufficient():
    rows = [NormalizedFinancials(ticker="T", fiscal_year=2024)]
    m = metrics(metric("debt_to_equity", series={2024: 0.3}))
    rules = {r.rule_id: r for r in _financial_health_rules(m, alerts(), rows)}
    # Current ratio has no calculator yet: it must degrade, not fabricate.
    assert rules["current_ratio"].status == INSUFFICIENT
    assert rules["debt_to_equity"].status == PASS


def test_financial_health_debt_bands_and_interest_coverage():
    rows = [_row()]
    m = metrics(
        metric("debt_to_equity", series={2024: 2.0}),
        metric("free_cash_flow", series={2024: 100.0}),
    )
    rules = {r.rule_id: r for r in _financial_health_rules(m, alerts(), rows)}
    assert rules["debt_to_equity"].status == FAIL  # 2.0x > 1.5x
    # ebit 150 / interest 20 = 7.5x
    assert rules["interest_coverage"].status == PASS
    assert rules["fcf_positive"].status == PASS


def test_shareholder_returns_and_payer_only_dividend_rules():
    m = metrics(
        metric("diluted_shares", cagr_5y=-1.0),
        metric("eps_diluted", cagr_5y=8.0),
        metric("dividends_paid", series={2024: 100.0}, trend="growing"),
        metric("free_cash_flow", series={2024: 400.0}),
    )
    rules = {r.rule_id: r for r in _shareholder_returns_rules(m, alerts())}
    assert rules["share_dilution"].status == PASS
    assert rules["per_share_accretion"].status == PASS
    assert rules["dividend_growth"].status == PASS
    assert rules["dividend_cover"].status == PASS  # 400 / 100 = 4x


def test_non_payer_dividend_rules_are_insufficient_not_fail():
    m = metrics(
        metric("diluted_shares", cagr_5y=0.0),
        metric("eps_diluted", cagr_5y=1.0),
    )
    rules = {r.rule_id: r for r in _shareholder_returns_rules(m, alerts())}
    assert rules["dividend_growth"].status == INSUFFICIENT
    assert rules["dividend_cover"].status == INSUFFICIENT


def test_valuation_uses_absolute_thresholds_only():
    m = metrics(
        metric("net_income", series={2024: 100.0}),
        metric("free_cash_flow", series={2024: 50.0}),
    )
    dcf = SimpleNamespace(margin_of_safety=0.30)
    rules = {r.rule_id: r for r in _valuation_rules(m, dcf, market_cap=1000.0)}
    assert rules["dcf_margin_of_safety"].status == PASS
    assert rules["pe_absolute"].status == PASS  # 1000 / 100 = 10x
    assert rules["fcf_yield"].status == PASS  # 50 / 1000 = 5%
    assert rules["earnings_sign"].status == PASS


def test_valuation_degrades_without_price():
    m = metrics(metric("net_income", series={2024: 100.0}))
    rules = {r.rule_id: r for r in _valuation_rules(m, None, market_cap=None)}
    assert rules["dcf_margin_of_safety"].status == INSUFFICIENT
    assert rules["pe_absolute"].status == INSUFFICIENT
    assert rules["fcf_yield"].status == INSUFFICIENT


def test_management_roic_persistence_needs_three_years():
    rules = {
        r.rule_id: r
        for r in _management_moat_rules(metrics(), [_row(2024), _row(2023)], None)
    }
    assert rules["roic_persistence"].status == INSUFFICIENT


def test_management_roic_persistence_and_red_flags():
    rows = [_row(year) for year in (2024, 2023, 2022, 2021, 2020)]
    rules = {r.rule_id: r for r in _management_moat_rules(metrics(), rows, ["a", "b"])}
    assert rules["roic_persistence"].status == PASS
    assert rules["management_red_flags"].status == FAIL
    assert rules["management_red_flags"].source_methodology == "buffett_clark"


# ---------------------------------------------------------------------------
# overall label (no master score)
# ---------------------------------------------------------------------------
def test_overall_is_a_label_not_a_number():
    strong = tuple(
        _build_dimension(key, [rule(PASS), rule(PASS)]) for key in DIMENSION_ORDER
    )
    assert _overall(strong) == "Strong"

    weak = tuple(
        _build_dimension(key, [rule(FAIL), rule(FAIL)]) for key in DIMENSION_ORDER
    )
    assert _overall(weak) == "Weak"

    insufficient = tuple(
        _build_dimension(key, [rule(INSUFFICIENT)]) for key in DIMENSION_ORDER
    )
    assert _overall(insufficient) == "Insufficient data"


# ---------------------------------------------------------------------------
# cross-dimension disagreements (>=7 strong vs <=3 weak)
# ---------------------------------------------------------------------------
def test_disagreement_fires_for_a_strong_growth_expensive_price():
    # AAPL-shaped: Growth 7, Valuation 2 — the pair the old >=8/<=4 rule missed.
    out = _disagreements(
        (
            dim("growth", "Growth", 7),
            dim("valuation", "Valuation", 2),
        )
    )
    assert out
    assert any("Growth" in message for message in out)
    assert any("Valuation" in message for message in out)


def test_disagreement_quiet_when_strong_side_is_only_six():
    # KO-shaped: Growth 6 does not clear the >=7 strong bar.
    out = _disagreements(
        (
            dim("growth", "Growth", 6),
            dim("valuation", "Valuation", 2),
        )
    )
    assert out == ()


def test_disagreement_fires_for_cheap_but_unprofitable():
    # F-shaped: Profitability 0, Valuation 7 — a non-adjacent pair.
    out = _disagreements(
        (
            dim("profitability", "Profitability", 0),
            dim("valuation", "Valuation", 7),
        )
    )
    assert out
    assert any("Profitability" in message for message in out)
    assert any("Valuation" in message for message in out)


def test_disagreement_fires_for_every_strong_weak_pair():
    # TSLA-shaped: one strong (Growth 9) against two weak (Valuation 2,
    # Shareholder Returns 0) yields one message per weak dimension.
    out = _disagreements(
        (
            dim("growth", "Growth", 9),
            dim("valuation", "Valuation", 2),
            dim("shareholder_returns", "Shareholder Returns", 0),
        )
    )
    assert len(out) == 2
    assert any("Valuation" in message for message in out)
    assert any("Shareholder Returns" in message for message in out)


def test_disagreement_groups_by_the_weak_dimension():
    # AAPL-shaped: five strong dimensions against a single weak Valuation
    # must produce ONE message, not one per strong side.
    out = _disagreements(
        (
            dim("growth", "Growth", 7),
            dim("profitability", "Profitability", 10),
            dim("financial_health", "Financial Health", 8),
            dim("valuation", "Valuation", 2),
            dim("shareholder_returns", "Shareholder Returns", 10),
            dim("management_moat", "Management/Moat", 7),
        )
    )
    assert len(out) == 1
    message = out[0]
    assert "Valuation" in message
    assert "Growth" in message and "Profitability" in message


def test_disagreement_one_message_per_weak_dimension():
    # F-shaped: Profitability 0 and Management/Moat 2 are both weak.
    out = _disagreements(
        (
            dim("growth", "Growth", 6),
            dim("profitability", "Profitability", 0),
            dim("financial_health", "Financial Health", 5),
            dim("valuation", "Valuation", 7),
            dim("shareholder_returns", "Shareholder Returns", 8),
            dim("management_moat", "Management/Moat", 2),
        )
    )
    assert len(out) == 2
    assert any(message.startswith("Profitability") for message in out)
    assert any(message.startswith("Management/Moat") for message in out)


def test_disagreement_needs_at_least_one_strong_dimension():
    assert (
        _disagreements(
            (
                dim("growth", "Growth", 5),
                dim("valuation", "Valuation", 2),
            )
        )
        == ()
    )


def test_disagreement_caps_the_named_strong_dimensions():
    # Five strong dimensions, one weak -> names at most three + a count.
    out = _disagreements(
        (
            dim("growth", "Growth", 9),
            dim("profitability", "Profitability", 9),
            dim("financial_health", "Financial Health", 9),
            dim("shareholder_returns", "Shareholder Returns", 9),
            dim("management_moat", "Management/Moat", 9),
            dim("valuation", "Valuation", 1),
        )
    )
    assert len(out) == 1
    assert "and 2 others" in out[0]
    # Only three dimension names appear before the "and N others" tail.
    assert "Growth" in out[0] and "Profitability" in out[0]
    assert "Financial Health" in out[0]
    assert "Shareholder Returns" not in out[0]
    assert "Management/Moat" not in out[0]


def test_join_names_is_deterministic_and_capped():
    assert _join_names(["Growth"]) == "Growth"
    assert _join_names(["Growth", "Valuation"]) == "Growth and Valuation"
    assert (
        _join_names(["Growth", "Valuation", "Profitability"])
        == "Growth, Valuation, and Profitability"
    )
    assert _join_names(["A", "B", "C", "D", "E"]) == "A, B, C, and 2 others"


def test_short_theme_prefers_growth_and_quality():
    assert _short_theme(["growth"]) == "growth"
    assert _short_theme(["growth", "management_moat"]) == "growth and quality"
    assert (
        _short_theme(["valuation", "shareholder_returns"])
        == "value and shareholder returns"
    )
    assert _short_theme([]) == "strength"


def test_disagreement_never_fires_on_insufficient_dimensions():
    # Both sides INSUFFICIENT -> no pair.
    assert (
        _disagreements(
            (
                dim("growth", "Growth", None),
                dim("valuation", "Valuation", None),
            )
        )
        == ()
    )
    # A strong side paired with an INSUFFICIENT side is not evaluable either.
    assert (
        _disagreements(
            (
                dim("growth", "Growth", 9),
                dim("valuation", "Valuation", None),
            )
        )
        == ()
    )


# ---------------------------------------------------------------------------
# service: determinism and read-only pricing
# ---------------------------------------------------------------------------
class _FakeRepository:
    def __init__(self, rows: list[NormalizedFinancials]) -> None:
        self._rows = list(rows)
        self.calls: list[tuple] = []

    def get_best_available(self, ticker: str, max_years: int = 10):
        self.calls.append(("get_best_available", ticker, max_years))
        return list(self._rows)

    def get_company_name(self, ticker: str) -> str:
        return "Test Co"

    # No ``list_all_facts``: the insights/alerts layer degrades to INSUFFICIENT.


class _FakePrices:
    def __init__(self, price: float = 100.0, market_cap: float = 1000.0) -> None:
        self.price = price
        self.market_cap = market_cap
        self.calls: list[str] = []

    def get_current_price(self, ticker: str) -> float:
        self.calls.append("get_current_price")
        return self.price

    def get_market_cap(self, ticker: str) -> float:
        self.calls.append("get_market_cap")
        return self.market_cap


def test_build_returns_six_dimensions_in_fixed_order():
    svc = ScorecardService(
        repository=_FakeRepository([_row(2024), _row(2023)]),
        price_service=_FakePrices(),
    )
    card = svc.build("t")
    assert card is not None
    assert card.ticker == "T"
    assert card.company == "Test Co"
    assert [d.key for d in card.dimensions] == list(DIMENSION_ORDER)
    # Methodology columns are carried through independently of the dimensions.
    assert card.methodologies


def test_build_sets_a_confidence_per_dimension_and_serializes_it():
    svc = ScorecardService(
        repository=_FakeRepository([_row(2024), _row(2023)]),
        price_service=_FakePrices(),
    )
    card = svc.build("t")
    assert card is not None
    allowed = {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW}
    assert all(d.confidence in allowed for d in card.dimensions)
    payload = card.to_dict()
    assert all("confidence" in d for d in payload["dimensions"])
    # The badge stays scorecard-level; confidence is per dimension.
    assert payload["data_quality"]


def test_build_is_deterministic():
    svc = ScorecardService(
        repository=_FakeRepository([_row(2024), _row(2023)]),
        price_service=_FakePrices(),
    )
    first = svc.build("T")
    second = svc.build("T")
    assert first is not None and second is not None
    assert first.generated == ""  # no clock, no randomness
    assert first.to_dict() == second.to_dict()


def test_build_unknown_ticker_returns_none():
    svc = ScorecardService(repository=_FakeRepository([]), price_service=_FakePrices())
    assert svc.build("NOPE") is None


def test_build_reads_prices_but_never_writes():
    prices = _FakePrices()
    svc = ScorecardService(
        repository=_FakeRepository([_row(2024)]), price_service=prices
    )
    svc.build("T")
    assert prices.calls, "expected a price read"
    assert set(prices.calls) <= {"get_current_price", "get_market_cap"}


# ---------------------------------------------------------------------------
# peer comparison (Phase 5B): additive annotation, never a scoring input
# ---------------------------------------------------------------------------
def _peer_stats(tmp_path, count: int = 12) -> PeerStatsService:
    """A synthetic artifact: ``count`` peers at P/E 10.. and net margin 5%.."""
    metrics = {
        "pe_ratio": {
            "n": count,
            "median": 10.0 + (count - 1) / 2,
            "unit": "multiple",
            "values": [10.0 + index for index in range(count)],
        },
        "net_margin": {
            "n": count,
            "median": 0.05 + (count - 1) / 200,
            "unit": "fraction",
            "values": [0.05 + index / 100 for index in range(count)],
        },
    }
    (tmp_path / "industry_widgets.json").write_text(
        json.dumps(
            {
                "level": "industry",
                "group": "Widgets",
                "slug": "widgets",
                "company_count": count,
                "generated_at": "2026-10-15T08:00:00Z",
                "metrics": metrics,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "sector_technology.json").write_text(
        json.dumps(
            {
                "level": "sector",
                "group": "Technology",
                "slug": "technology",
                "company_count": count,
                "generated_at": "2026-10-15T08:00:00Z",
                "metrics": metrics,
            }
        ),
        encoding="utf-8",
    )
    return PeerStatsService(tmp_path)


class _FakeFactsRepository:
    """Repository exposing a small, self-consistent annual fact history."""

    def __init__(self, rows: list[NormalizedFinancials]) -> None:
        self._rows = list(rows)

    def get_best_available(self, ticker: str, max_years: int = 10):
        return list(self._rows)

    def get_company_name(self, ticker: str) -> str:
        return "Test Co"

    def list_all_facts(self, ticker: str, fiscal_period: str = "FY", max_years=None):
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


def _fact_rows() -> list[NormalizedFinancials]:
    """Six growing years: net margin 13.3%, ROE 33.3% in the latest."""
    return [
        _row(
            2020 + index,
            revenue=100.0 + 10 * index,
            net_income=10.0 + 2 * index,
            stockholders_equity=40.0 + 4 * index,
            sector="Technology",
            industry="Widgets",
        )
        for index in range(6)
    ]


def _peered_rule(card, rule_id: str):
    for dimension in card.dimensions:
        for rule in dimension.rules:
            if rule.rule_id == rule_id:
                return rule
    raise AssertionError(f"rule {rule_id} not found")


def test_attach_peers_annotates_only_the_mapped_rules(tmp_path):
    peers = _peer_stats(tmp_path)
    dimension = _build_dimension(
        "profitability",
        [rule(PASS, rule_id="net_margin"), rule(PASS, rule_id="roic")],
    )
    (annotated,) = _attach_peers(
        (dimension,),
        peers,
        sector="Technology",
        industry="Widgets",
        metrics=metrics(metric("net_margin", series={2025: 0.105})),
        market_cap=1000.0,
    )
    assert annotated.peer_group == "Widgets"
    assert annotated.peer_group_level == "industry"
    assert annotated.peer_group_size == 12
    net_margin, roic = annotated.rules
    assert net_margin.peer_median == "10.5%"  # median of 5%..16%
    assert net_margin.peer_percentile == pytest.approx(0.5)
    # A rule whose metric is not in the artifact is left untouched.
    assert roic.peer_median is None
    assert roic.peer_percentile is None
    assert annotated.score == dimension.score


def test_attach_peers_is_a_noop_without_a_group(tmp_path):
    peers = _peer_stats(tmp_path)
    dimension = _build_dimension("valuation", [rule(PASS, rule_id="pe_absolute")])
    (annotated,) = _attach_peers(
        (dimension,),
        peers,
        sector=None,
        industry=None,
        metrics=metrics(),
        market_cap=None,
    )
    assert annotated == dimension
    assert annotated.peer_group is None


def test_build_populates_peer_fields_without_changing_the_score(tmp_path):
    rows = _fact_rows()
    peers = _peer_stats(tmp_path)
    svc = ScorecardService(
        repository=_FakeFactsRepository(rows),
        price_service=_FakePrices(price=32.0, market_cap=320.0),
        peer_stats=peers,
    )
    card = svc.build("T")
    assert card is not None

    # P/E = 320 / 20 = 16.0 -> scored, and ranked against the artifact.
    per = _peered_rule(card, "pe_absolute")
    assert per.peer_percentile == pytest.approx(round(6.5 / 12, 4))
    assert per.peer_median == "15.50x"
    roe = _peered_rule(card, "roe")
    assert roe.peer_percentile is None  # the artifact has no ROE column
    assert roe.peer_median is None
    # Every dimension carries the resolved group.
    assert {d.peer_group for d in card.dimensions} == {"Widgets"}
    assert {d.peer_group_size for d in card.dimensions} == {12}

    plain = ScorecardService(
        repository=_FakeFactsRepository(rows),
        price_service=_FakePrices(price=32.0, market_cap=320.0),
        peer_stats=PeerStatsService(tmp_path / "empty"),
    ).build("T")
    assert plain is not None
    assert [d.score for d in card.dimensions] == [d.score for d in plain.dimensions]
    assert all(
        rule.peer_percentile is None
        for dimension in plain.dimensions
        for rule in dimension.rules
    )
    assert {d.peer_group for d in plain.dimensions} == {None}


def test_build_serializes_the_peer_fields(tmp_path):
    svc = ScorecardService(
        repository=_FakeFactsRepository(_fact_rows()),
        price_service=_FakePrices(price=32.0, market_cap=320.0),
        peer_stats=_peer_stats(tmp_path),
    )
    payload = svc.build("T").to_dict()
    rules = [rule for d in payload["dimensions"] for rule in d["rules"]]
    assert any(rule["peer_median"] for rule in rules)
    assert any(rule["peer_percentile"] is not None for rule in rules)
    assert all("peer_group" in d for d in payload["dimensions"])


def test_build_without_an_artifact_still_works(tmp_path):
    svc = ScorecardService(
        repository=_FakeFactsRepository(_fact_rows()),
        price_service=_FakePrices(),
        peer_stats=PeerStatsService(tmp_path / "missing"),
    )
    card = svc.build("T")
    assert card is not None
    assert all(dimension.peer_group is None for dimension in card.dimensions)


def test_build_survives_a_broken_peer_service(tmp_path):
    class _Broken:
        def group_for(self, **_):
            raise RuntimeError("boom")

    svc = ScorecardService(
        repository=_FakeFactsRepository(_fact_rows()),
        price_service=_FakePrices(),
        peer_stats=_Broken(),
    )
    card = svc.build("T")
    assert card is not None  # a broken peer source never breaks the card
    assert {d.peer_group for d in card.dimensions} == {None}
