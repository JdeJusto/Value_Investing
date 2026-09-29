"""Unit tests: screener filters, ranking, signals and opportunity engine.

Uses mock analytics/intelligence outputs — no providers, no network.
"""

from dataclasses import replace
from typing import Optional

from backend.screener.filters import ScreenCriteria, from_kwargs, matches
from backend.screener.opportunity_engine import (
    best_opportunity,
    detect_opportunities,
)
from backend.screener.ranking_engine import margin_of_safety_score, rank_score
from backend.screener.screener_service import ScreenerService
from backend.screener.signals import generate_signal


# ----------------------------------------------------------------------
# Builders of mock analysis outputs
# ----------------------------------------------------------------------
def _analysis(
    ticker: str,
    buffett: float = 82.0,
    moat_type: str = "STRONG",
    moat_score: float = 78.0,
    total_score: float = 80.0,
    rating: str = "A",
    confidence: str = "HIGH",
    margin: float = 0.25,
    market_cap: float = 300e9,
    roic: float = 0.17,
    cagr: float = 0.11,
    debt_equity: float = 0.4,
    revenue_cv: float = 0.2,
    sector: str = "Technology",
    industry: str = "Software",
    delta: dict | None = None,
    **pillars,
) -> dict:
    deltas = {
        "revenue_growth_last": 0.05,
        "revenue_growth_prev": 0.05,
        "revenue_growth_delta": 0.0,
        "gross_margin_delta": 0.0,
        "roic_delta": 0.0,
        "fcf_delta": 0.0,
    }
    if delta is not None:
        deltas.update(delta)
    breakdown = {
        "profitability": 88.0,
        "financial_strength": 90.0,
        "cash_generation": 85.0,
        "stability": 82.0,
    }
    breakdown.update(pillars)
    metrics = {
        "roic_mean": roic,
        "roe_mean": 0.20,
        "revenue_cagr": cagr,
        "revenue_cv": revenue_cv,
        "gross_margin_cv": 0.05,
        "gross_margin_trend": 0.008,
        "capital_intensity": 0.05,
        "positive_fcf_ratio": 0.9,
        "fcf_growth": 0.1,
        "earnings_cv": 0.2,
        "max_yoy_decline": -0.05,
        "debt_to_equity": debt_equity,
        "debt_trend": -0.10,
        "net_income_change": 0.05,
        "interest_coverage": 12.0,
        "retained_earnings_positive": True,
        "book_value_per_share": 25.0,
        "owner_earnings": 5e9,
        "shares_outstanding": 1e9,
    }
    return {
        "ticker": ticker,
        "market_cap": market_cap,
        "current_price": 90.0,
        "dcf_value": 120.0,
        "dcf_margin_of_safety": margin,
        "buffett_score": buffett,
        "buffett_breakdown": breakdown,
        "moat_analysis": {"moat_score": moat_score, "moat_type": moat_type},
        "composite_score": {
            "total_score": total_score,
            "rating": rating,
            "confidence": confidence,
        },
        "quality_metrics": metrics,
        "delta_metrics": deltas,
        "anomalies": [],
        "insight": ["Low debt and high interest coverage"],
        "sector": sector,
        "industry": industry,
    }


class MockAnalyzer:
    def __init__(self, **companies):
        self._companies = companies

    def __call__(self, ticker: str):
        company = self._companies.get(ticker)
        return dict(company) if company is not None else None


# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------
def test_filter_by_moat_accepts_equal_or_better():
    criteria = from_kwargs(moat="MODERATE")
    assert matches(_analysis("STRONG_CO", moat_type="STRONG"), criteria)
    assert matches(_analysis("MOD_CO", moat_type="MODERATE"), criteria)
    assert not matches(_analysis("WEAK_CO", moat_type="WEAK"), criteria)


def test_filter_by_scores_and_ratios():
    base = dict(min_buffett_score=75, min_roic=0.15, max_debt_ratio=1.0)
    criteria = from_kwargs(**base)
    assert matches(_analysis("GOOD"), criteria)
    assert not matches(_analysis("LOW_ROIC", roic=0.08), criteria)
    assert not matches(_analysis("HIGH_DEBT", debt_equity=1.8), criteria)
    assert not matches(_analysis("LOW_BUFFETT", buffett=50), criteria)


def test_filter_by_market_cap_range_and_growth():
    criteria = from_kwargs(
        min_market_cap=100e9, max_market_cap=500e9, min_revenue_growth=0.10
    )
    assert matches(_analysis("GOOD"), criteria)
    assert not matches(_analysis("TINY", market_cap=10e9), criteria)
    assert not matches(_analysis("SLOW", cagr=0.02), criteria)


def test_filter_by_sector_industry_confidence_and_total():
    criteria = from_kwargs(sector="Technology", industry="Software")
    assert matches(_analysis("GOOD"), criteria)
    assert not matches(_analysis("FIN", sector="Financials"), criteria)

    conf = from_kwargs(confidence="HIGH")
    assert matches(_analysis("GOOD"), conf)
    assert not matches(_analysis("LOW_CONF", confidence="MEDIUM"), conf)

    total = from_kwargs(min_score=85)
    assert not matches(_analysis("GOOD_MEDIUM", total_score=80), total)
    assert matches(_analysis("STRONG", total_score=88), total)


def test_filter_margin_of_safety_and_tickers():
    criteria = from_kwargs(min_margin_of_safety=0.15, tickers={"AAA"})
    assert not matches(_analysis("BBB", margin=0.10), criteria)
    assert not matches(_analysis("AAA", margin=0.10), criteria)
    assert matches(_analysis("AAA", margin=0.20), criteria)


def test_from_kwargs_ignores_unknown_and_none():
    criteria = from_kwargs(moat="STRONG", unknown_arg=42, min_roic=None)
    assert criteria.moat == "STRONG"
    assert criteria.min_roic is None
    assert criteria.min_total_score is None
    assert ScreenCriteria() == replace(criteria, moat=None)


# ----------------------------------------------------------------------
# Ranking engine
# ----------------------------------------------------------------------
def test_rank_score_weights_and_saturation():
    good = _analysis("GOOD", total_score=90, margin=0.5, confidence="HIGH")
    base = _analysis("BASE", total_score=60, margin=0.0, confidence="MEDIUM")
    assert margin_of_safety_score(_analysis("SAT", margin=0.5)) == 1.0
    assert margin_of_safety_score(_analysis("NEG", margin=-0.1)) == 0.0
    assert rank_score(good) > rank_score(base)
    assert 0 <= rank_score(good) <= 100


def test_rank_score_prefers_margin_of_safety():
    expensive = _analysis("EXP", total_score=75, margin=0.05)
    cheap = _analysis("CHE", total_score=70, margin=0.35)
    assert rank_score(cheap) > rank_score(expensive)


def test_rank_score_prefers_higher_confidence():
    low_conf = _analysis("LO", total_score=72, confidence="LOW")
    high_conf = _analysis("HI", total_score=72, confidence="HIGH")
    assert rank_score(high_conf) > rank_score(low_conf)


# ----------------------------------------------------------------------
# Signals
# ----------------------------------------------------------------------
def test_signal_buy_for_high_rank_opportunity():
    item = _analysis("KO", buffett=85, margin=0.3)
    opportunity = best_opportunity(item)
    signal = generate_signal(dict(item, opportunity=opportunity), rank_score(item))
    assert signal["signal"] == "BUY"
    assert signal["confidence"] == "HIGH"


def test_signal_avoid_for_weak_buffett():
    item = _analysis("LOSS", buffett=30)
    signal = generate_signal(item, rank_score(item))
    assert signal["signal"] == "AVOID"


def test_signal_watchlist_and_hold():
    watch = _analysis("W", buffett=70, total_score=68, margin=0.20)
    assert generate_signal(watch, rank_score(watch))["signal"] in ("WATCHLIST", "BUY")
    hold = _analysis("H", buffett=60, total_score=50, margin=0.0, confidence="LOW")
    assert generate_signal(hold, rank_score(hold))["signal"] in ("HOLD", "WATCHLIST")


# ----------------------------------------------------------------------
# Opportunity engine
# ----------------------------------------------------------------------
def test_undervalued_quality_detected():
    item = _analysis("MSFT", buffett=85, moat_type="STRONG", margin=0.30)
    opportunities = detect_opportunities(item)
    types = [o["type"] for o in opportunities]
    assert "UNDERVALUED_QUALITY" in types
    candidate = next(o for o in opportunities if o["type"] == "UNDERVALUED_QUALITY")
    assert candidate["confidence"] == "HIGH"
    assert any("margin of safety" in r for r in candidate["reason"])


def test_undervalued_quality_requires_discount():
    item = _analysis("MSFT", buffett=85, margin=0.05)
    assert all(o["type"] != "UNDERVALUED_QUALITY" for o in detect_opportunities(item))


def test_compounders_detected():
    item = _analysis("COST", roic=0.22, cagr=0.14)
    types = [o["type"] for o in detect_opportunities(item)]
    assert "COMPOUNDERS" in types


def test_turnaround_detected():
    item = _analysis(
        "GE",
        buffett=55,
        moat_type="WEAK",
        margin=0.05,
    )
    metrics = item["quality_metrics"]
    metrics.update(
        {
            "gross_margin_trend": 0.01,
            "debt_trend": -0.20,
            "net_income_change": 0.60,
        }
    )
    types = [o["type"] for o in detect_opportunities(item)]
    assert "TURNAROUNDS" in types


def test_special_situation_deep_value():
    item = _analysis("BANK", current_price=10.0)
    metrics = item["quality_metrics"]
    metrics["book_value_per_share"] = 50.0
    item["current_price"] = 10.0
    types = [o["type"] for o in detect_opportunities(item)]
    assert "SPECIAL_SITUATIONS" in types


def test_special_situation_volatile_quality():
    item = _analysis("VOL", earnings_cv=0.7)
    metrics = item["quality_metrics"]
    metrics["earnings_cv"] = 0.7
    item["current_price"] = 100.0
    metrics["book_value_per_share"] = 200.0
    types = [o["type"] for o in detect_opportunities(item)]
    assert "SPECIAL_SITUATIONS" in types


# ----------------------------------------------------------------------
# Screener service
# ----------------------------------------------------------------------
def test_screener_run_ranks_and_orders():
    analyzer = MockAnalyzer(
        AAA=_analysis("AAA", total_score=90, margin=0.4),
        BBB=_analysis("BBB", total_score=70, margin=0.0),
        NODATA=None,
    )
    service = ScreenerService(analyzer, universe=["AAA", "BBB", "NODATA"])
    results = service.run()
    assert [r.ticker for r in results] == ["AAA", "BBB"]
    assert results[0].rank == 1
    assert results[0].rank_score > results[1].rank_score
    row = results[0].to_dict()
    assert row["moat"] == "STRONG"
    assert row["rating"] == "A"
    assert row["signal"] == "BUY"
    assert row["opportunity_type"] in (
        "UNDERVALUED_QUALITY",
        "COMPOUNDERS",
        "SPECIAL_SITUATIONS",
        None,
    )
    assert row["reasons"]


def test_screener_filters_before_ranking():
    analyzer = MockAnalyzer(
        GOOD=_analysis("GOOD", buffett=85),
        WEAK=_analysis("WEAK", buffett=45),
    )
    service = ScreenerService(analyzer, universe=["GOOD", "WEAK"])
    results = service.run(min_buffett_score=60)
    assert [r.ticker for r in results] == ["GOOD"]


def test_screener_top_n():
    analyzer = MockAnalyzer(
        **{f"T{i:02d}": _analysis(f"T{i:02d}", total_score=50 + i) for i in range(10)}
    )
    service = ScreenerService(analyzer, universe=[f"T{i:02d}" for i in range(10)])
    top = service.top_n(3)
    assert len(top) == 3
    assert top[0].ticker == "T09"


def test_screener_opportunities_endpoint():
    analyzer = MockAnalyzer(
        UND=_analysis("UND", buffett=85, margin=0.35),
        NORM=_analysis("NORM", margin=0.0, roic=0.06, cagr=0.01, buffett=45),
    )
    service = ScreenerService(analyzer, universe=["UND", "NORM"])
    opportunities = service.opportunities()
    assert any(o["ticker"] == "UND" for o in opportunities)
    assert all(o["ticker"] != "NORM" for o in opportunities)
    assert all(o["type"] and o["reason"] for o in opportunities)


def test_screener_enrichment_attaches_sector():
    analyzer = MockAnalyzer(AAA=_analysis("AAA"))
    service = ScreenerService(
        analyzer,
        universe=["AAA"],
        enrich=lambda ticker, item: {**item, "sector": "Energy"},
    )
    result = service.run(sector="Energy")
    assert result[0].ticker == "AAA"


# ----------------------------------------------------------------------
# Fundamental momentum in ranking
# ----------------------------------------------------------------------
def test_momentum_factor_improves_rank():
    from backend.screener.ranking_engine import fundamental_momentum

    flat = _analysis("FLAT")
    surging = _analysis(
        "SURGE",
        delta={
            "revenue_growth_delta": 0.05,
            "gross_margin_delta": 0.02,
            "roic_delta": 0.04,
            "fcf_delta": 0.30,
        },
    )
    deteriorating = _analysis(
        "DOWN",
        delta={
            "revenue_growth_delta": -0.05,
            "gross_margin_delta": -0.03,
            "roic_delta": -0.06,
            "fcf_delta": -0.40,
        },
    )
    assert fundamental_momentum(surging) > 0.5
    assert fundamental_momentum(deteriorating) < 0.5
    assert rank_score(surging) > rank_score(flat) > rank_score(deteriorating)


def test_rank_score_neutral_momentum_without_deltas():
    from backend.screener.ranking_engine import fundamental_momentum

    item = _analysis("NO_DELTAS")
    item["delta_metrics"] = {}
    assert fundamental_momentum(item) == 0.5


# ----------------------------------------------------------------------
# Calibrated ranking (cross-sectional)
# ----------------------------------------------------------------------

def _rank_dict(ticker, buffett=80, total=80, margin=0.3, moat_type="STRONG", moat_score=78,
               delta=None, fcf=10e9, debt_to_equity=0.4, interest_coverage=12.0,
               roic=0.15, cagr=0.10):
    """Build an analysis dict suitable for calibrated_rank."""
    d = _analysis(
        ticker,
        buffett=buffett,
        total_score=total,
        margin=margin,
        moat_type=moat_type,
        moat_score=moat_score,
        delta=delta,
        debt_equity=debt_to_equity,
        roic=roic,
        cagr=cagr,
    )
    d["fcf"] = fcf
    d["quality_metrics"] = {
        "roic_mean": 0.15,
        "roe_mean": 0.20,
        "revenue_cagr": 0.10,
        "revenue_cv": 0.2,
        "gross_margin_cv": 0.05,
        "gross_margin_trend": 0.005,
        "capital_intensity": 0.05,
        "positive_fcf_ratio": 0.9,
        "fcf_growth": 0.1,
        "earnings_cv": 0.2,
        "max_yoy_decline": -0.05,
        "debt_to_equity": debt_to_equity,
        "debt_trend": -0.10,
        "net_income_change": 0.05,
        "interest_coverage": interest_coverage,
        "retained_earnings_positive": True,
        "book_value_per_share": 25.0,
        "owner_earnings": 5e9,
        "shares_outstanding": 1e9,
    }
    return d


def test_calibrated_rank_spreads_scores():
    from backend.screener.ranking_engine import calibrated_rank, CALIBRATION_MIN, CALIBRATION_MAX

    items = [_rank_dict(f"T{i}", total=40 + i * 5) for i in range(10)]
    ranks = [calibrated_rank(it, items) for it in items]
    assert all(CALIBRATION_MIN <= r <= CALIBRATION_MAX for r in ranks)
    # The highest-quality company should have the highest rank.
    assert ranks[-1] > ranks[0]


def test_calibrated_rank_quality_leads_over_cheapness():
    """A high-quality (low margin) company outranks a cheaper one (low quality)."""
    from backend.screener.ranking_engine import calibrated_rank

    quality = _rank_dict("QUAL", buffett=85, total=90, margin=0.0)   # no MOS
    cheap = _rank_dict("CHEAP", buffett=40, total=40, margin=0.30)  # high MOS
    items = [quality, cheap]
    assert calibrated_rank(quality, items) > calibrated_rank(cheap, items)


def test_health_cap_penalizes_negative_fcf():
    """Negative FCF caps even a fundamentally strong company at the cap."""
    from backend.screener.ranking_engine import calibrated_rank, LEVERAGED_RANK_CAP

    # "BEST" has the strongest fundamentals but burns cash.
    best = _rank_dict("BEST", buffett=95, total=99, roic=0.30, cagr=0.25, fcf=-2e9)
    weak = _rank_dict("WEAK", buffett=30, total=25, roic=0.05, cagr=0.01, fcf=1e9)
    items = [weak, best]
    top = calibrated_rank(best, items)
    assert top == LEVERAGED_RANK_CAP
    assert calibrated_rank(weak, items) < top


def test_health_cap_penalizes_high_debt():
    from backend.screener.ranking_engine import health_cap, LEVERAGED_DEBT_CAP, LEVERAGED_RANK_CAP

    low_debt = _rank_dict("LOW", debt_to_equity=0.4)
    high_debt = _rank_dict("HIGH", debt_to_equity=2.0)
    assert health_cap(low_debt) > LEVERAGED_RANK_CAP
    assert health_cap(high_debt) == LEVERAGED_DEBT_CAP


def test_health_cap_penalizes_weak_coverage():
    from backend.screener.ranking_engine import health_cap, LEVERAGED_COVERAGE_CAP, LEVERAGED_RANK_CAP

    strong = _rank_dict("STRONG", interest_coverage=12.0)
    weak = _rank_dict("WEAK", interest_coverage=2.5)
    assert health_cap(strong) > LEVERAGED_RANK_CAP
    assert health_cap(weak) == LEVERAGED_COVERAGE_CAP


def test_health_cap_allows_good_health():
    from backend.screener.ranking_engine import health_cap, CALIBRATION_MAX

    item = _rank_dict("GOOD", fcf=10e9, debt_to_equity=0.5, interest_coverage=15.0)
    assert health_cap(item) == CALIBRATION_MAX


def test_health_cap_applies_most_restrictive_of_ALL_matching_caps():
    """The bug: only the first matching condition was applied. A company
    with several problems must be capped by the most restrictive of them."""
    from backend.screener.ranking_engine import (
        health_cap,
        LEVERAGED_COVERAGE_CAP,
        LEVERAGED_DEBT_CAP,
        LEVERAGED_RANK_CAP,
    )

    # Negative FCF + high leverage + weak coverage all at once → coverage cap.
    worst = _rank_dict(
        "WORST", fcf=-2e9, debt_to_equity=2.0, interest_coverage=2.0
    )
    assert health_cap(worst) == LEVERAGED_COVERAGE_CAP
    assert health_cap(worst) < LEVERAGED_DEBT_CAP < LEVERAGED_RANK_CAP

    # Negative FCF + high leverage (no coverage data) → debt cap.
    mixed = _rank_dict("MIXED", fcf=-2e9, debt_to_equity=2.0, interest_coverage=12.0)
    assert health_cap(mixed) == LEVERAGED_DEBT_CAP

    # Negative coverage (loss-making with interest expense) must also cap.
    loss = _rank_dict("LOSS", fcf=5e9, debt_to_equity=0.4, interest_coverage=-1.5)
    assert health_cap(loss) == LEVERAGED_COVERAGE_CAP


# ----------------------------------------------------------------------
# New opportunity detectors
# ----------------------------------------------------------------------
def test_inflection_point_detected_on_recovery():
    item = _analysis(
        "REC",
        buffett=45,
        moat_type="WEAK",
        delta={
            "revenue_growth_last": 0.08,
            "revenue_growth_prev": -0.05,
            "net_income_change": 0.4,
        },
    )
    types = [o["type"] for o in detect_opportunities(item)]
    assert "INFLECTION_POINT" in types


def test_fundamental_acceleration_detected():
    item = _analysis(
        "ACCEL",
        delta={
            "revenue_growth_delta": 0.04,
            "roic_delta": 0.02,
        },
    )
    types = [o["type"] for o in detect_opportunities(item)]
    assert "FUNDAMENTAL_ACCELERATION" in types


def test_fundamental_acceleration_requires_cash_generation():
    item = _analysis(
        "ACCEL",
        roic=0.10,
        delta={"revenue_growth_delta": 0.04, "roic_delta": 0.02},
    )
    metrics = item["quality_metrics"]
    metrics["positive_fcf_ratio"] = 0.3
    assert all(
        o["type"] != "FUNDAMENTAL_ACCELERATION" for o in detect_opportunities(item)
    )


def test_quality_with_trigger_detected():
    item = _analysis(
        "QTRIG",
        buffett=80,
        moat_type="STRONG",
        delta={"gross_margin_delta": 0.015},
    )
    candidate = best_opportunity(item)
    assert candidate is not None
    qwt = [o for o in detect_opportunities(item) if o["type"] == "QUALITY_WITH_TRIGGER"]
    assert qwt
    assert any("trigger" in r for r in qwt[0]["reason"])


def test_quality_with_trigger_needs_quality_and_moat():
    weak = _analysis(
        "QW",
        buffett=55,
        moat_type="WEAK",
        delta={"gross_margin_delta": 0.02},
    )
    assert all(o["type"] != "QUALITY_WITH_TRIGGER" for o in detect_opportunities(weak))


# ----------------------------------------------------------------------
# Signal triggers
# ----------------------------------------------------------------------
def test_signal_trigger_positive_margin_expansion():
    item = _analysis("M", delta={"gross_margin_delta": 0.02})
    signal = generate_signal(item, rank_score(item))
    assert signal["trigger"] == "MARGIN_EXPANSION"


def test_signal_trigger_prefers_strongest_positive():
    item = _analysis(
        "S",
        delta={
            "gross_margin_delta": 0.02,
            "revenue_growth_delta": 0.06,
            "roic_delta": -0.01,
        },
    )
    signal = generate_signal(item, rank_score(item))
    assert signal["trigger"] == "REVENUE_ACCELERATION"


def test_signal_trigger_none_when_only_declining():
    # Deliberate policy: deterioration is not a positive trigger event, so a
    # company where every delta is negative emits no trigger (SELL_WARNING
    # and anomaly reporting cover deterioration instead).
    item = _analysis(
        "D",
        delta={
            "gross_margin_delta": -0.02,
            "revenue_growth_delta": -0.03,
        },
    )
    signal = generate_signal(item, rank_score(item))
    assert signal["trigger"] is None


def test_signal_trigger_none_without_delta_data():
    item = _analysis("N")
    item["delta_metrics"] = {}
    signal = generate_signal(item, rank_score(item))
    assert signal["trigger"] is None
