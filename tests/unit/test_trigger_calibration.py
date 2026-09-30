"""Tests for calibrated, persistence-aware positive triggers.

The trigger policy (see backend.screener.signals):
- TRIGGER_EVENT fires only for the dominant *positive* improvement.
- A positive delta must clear both the absolute floor and a cross-sectional
  percentile floor computed over the analyzed universe.
- Improvements should be persistent where the data allows (two consecutive
  periods), and an FCF surge needs positive FCF.
- Deterioration is never a trigger.
"""

from backend.alerts import TRIGGER_EVENT, evaluate_company, run
from backend.screener.signals import (
    FCF_SURGE_FLOOR,
    MARGIN_EXPANSION_FLOOR,
    REVENUE_ACCELERATION_FLOOR,
    ROIC_IMPROVEMENT_FLOOR,
    calibrate_trigger_thresholds,
    detect_trigger,
)


def make_item(deltas, fcf=1.0):
    """A minimal analysis-shaped item for trigger logic."""
    return {
        "ticker": "X",
        "composite_score": {"total_score": 80.0, "confidence": "HIGH"},
        "buffett_score": 80.0,
        "fcf": fcf,
        "delta_metrics": deltas,
    }


class TestAbsoluteFloors:
    def test_margin_at_floor_fires(self):
        item = make_item({"gross_margin_delta": MARGIN_EXPANSION_FLOOR})
        assert detect_trigger(item) == "MARGIN_EXPANSION"

    def test_margin_under_floor_does_not_fire(self):
        item = make_item({"gross_margin_delta": MARGIN_EXPANSION_FLOOR - 0.005})
        assert detect_trigger(item) is None

    def test_revenue_floor(self):
        assert (
            detect_trigger(
                make_item({"revenue_growth_delta": REVENUE_ACCELERATION_FLOOR})
            )
            == "REVENUE_ACCELERATION"
        )
        assert (
            detect_trigger(
                make_item({"revenue_growth_delta": REVENUE_ACCELERATION_FLOOR - 0.01})
            )
            is None
        )

    def test_roic_floor(self):
        assert (
            detect_trigger(make_item({"roic_delta": ROIC_IMPROVEMENT_FLOOR}))
            == "ROIC_IMPROVEMENT"
        )
        assert (
            detect_trigger(make_item({"roic_delta": ROIC_IMPROVEMENT_FLOOR - 0.005}))
            is None
        )

    def test_fcf_surge_floor_and_positive_fcf(self):
        item = make_item({"fcf_delta": FCF_SURGE_FLOOR}, fcf=5.0)
        assert detect_trigger(item) == "FCF_SURGE"
        # A surge from a negative FCF base is not an improvement worth an alert.
        assert (
            detect_trigger(make_item({"fcf_delta": FCF_SURGE_FLOOR}, fcf=-1.0)) is None
        )


class TestDominance:
    def test_strongest_positive_wins(self):
        item = make_item(
            {
                "gross_margin_delta": 0.05,
                "revenue_growth_delta": 0.15,
                "roic_delta": 0.04,
            }
        )
        assert detect_trigger(item) == "REVENUE_ACCELERATION"


class TestNoNegativeTriggers:
    def test_all_declining_is_none(self):
        item = make_item(
            {
                "gross_margin_delta": -0.05,
                "revenue_growth_delta": -0.10,
                "roic_delta": -0.05,
                "fcf_delta": -0.30,
            }
        )
        assert detect_trigger(item) is None


class TestPersistence:
    def test_margin_blocked_when_prior_period_declined(self):
        item = make_item(
            {
                "gross_margin_delta": 0.04,
                "gross_margin_delta_prev": -0.02,
            }
        )
        assert detect_trigger(item) is None

    def test_margin_fires_when_prior_period_improved(self):
        item = make_item(
            {
                "gross_margin_delta": 0.04,
                "gross_margin_delta_prev": 0.01,
            }
        )
        assert detect_trigger(item) == "MARGIN_EXPANSION"

    def test_margin_fires_without_prior_period_data(self):
        # Three periods are required to check persistence; with fewer the
        # current-period evidence stands on its own.
        item = make_item({"gross_margin_delta": 0.04})
        assert detect_trigger(item) == "MARGIN_EXPANSION"

    def test_revenue_blocked_when_not_two_consecutive_growth_periods(self):
        item = make_item(
            {
                "revenue_growth_delta": 0.10,
                "revenue_growth_last": 0.05,
                "revenue_growth_prev": -0.02,
            }
        )
        assert detect_trigger(item) is None

    def test_revenue_fires_with_two_consecutive_growth_periods(self):
        item = make_item(
            {
                "revenue_growth_delta": 0.10,
                "revenue_growth_last": 0.08,
                "revenue_growth_prev": 0.04,
            }
        )
        assert detect_trigger(item) == "REVENUE_ACCELERATION"


class TestCalibration:
    def test_small_universe_uses_absolute_floors(self):
        items = [
            make_item(d) for d in ({"gross_margin_delta": 0.03}, {"roic_delta": 0.05})
        ]
        thresholds = calibrate_trigger_thresholds(items)
        # Isolated runs fall back to the absolute floors, so a single-company
        # evaluation still behaves deterministically.
        assert thresholds["MARGIN_EXPANSION"] == MARGIN_EXPANSION_FLOOR
        assert thresholds["ROIC_IMPROVEMENT"] == ROIC_IMPROVEMENT_FLOOR

    def test_percentile_raises_the_bar(self):
        # A large universe with mostly large positive deltas pushes the
        # threshold above the absolute floors.
        deltas = [{"gross_margin_delta": 0.08}] * 40 + [
            {"gross_margin_delta": 0.06}
        ] * 40
        items = [make_item(d) for d in deltas]
        thresholds = calibrate_trigger_thresholds(items)
        assert thresholds["MARGIN_EXPANSION"] > MARGIN_EXPANSION_FLOOR

    def test_never_below_absolute_floor(self):
        plink = [{"gross_margin_delta": 0.025}] * 50
        items = [make_item(d) for d in plink]
        thresholds = calibrate_trigger_thresholds(items)
        assert thresholds["MARGIN_EXPANSION"] >= MARGIN_EXPANSION_FLOOR

    def test_calibrated_threshold_is_applied(self):
        # Wide-spread universe: the 92nd-percentile floor sits above the
        # mid-point values, so the calibrated bar keeps only the biggest delta.
        items = [
            make_item({"gross_margin_delta": v}) for v in (0.03, 0.04, 0.05, 0.06, 0.07)
        ]
        thresholds = calibrate_trigger_thresholds(items, min_samples=5)
        firing = [i for i in items if detect_trigger(i, thresholds=thresholds)]
        assert len(firing) == 1


class TestAlertEngineIntegration:
    def test_run_calibrates_surges_down(self):
        # Every FCF delta would pass the absolute 20% floor. The calibrated
        # 92nd-percentile bar keeps only the top of the universe plus the
        # clear outlier.
        uniform = {
            f"T{i}": make_item({"fcf_delta": 0.20 + 0.12 * i / 39}, fcf=10.0)
            for i in range(40)
        }
        analyses = uniform | {"BIG": make_item({"fcf_delta": 9.0}, fcf=10.0)}
        alerts = run(analyses)
        trigger_tickers = {a.ticker for a in alerts if a.alert_type == TRIGGER_EVENT}
        assert "BIG" in trigger_tickers
        assert len(trigger_tickers) <= 6

    def test_evaluate_company_defaults_to_floors(self):
        item = make_item({"gross_margin_delta": 0.03})
        types = [a.alert_type for a in evaluate_company("X", item, previous=None)]
        assert TRIGGER_EVENT in types

    def test_dedup_preserves_one_trigger_per_ticker(self):
        analyses = {
            "X": make_item({"gross_margin_delta": 0.03}),
            "Y": make_item({"fcf_delta": 0.9}, fcf=5.0),
        }
        alerts = run(analyses)
        assert sum(1 for a in alerts if a.alert_type == TRIGGER_EVENT) == 2
