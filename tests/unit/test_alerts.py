from backend.alerts import (
    BUY_SIGNAL,
    SELL_WARNING,
    TRIGGER_EVENT,
    Alert,
    ConsoleNotifier,
    Notifier,
    dedupe,
    evaluate_company,
    notify_all,
    run,
    sell_warning_score_drop,
    to_dicts,
    trigger_label,
)
from backend.screener.ranking_engine import rank_score
from backend.screener.signals import detect_trigger


def make_analysis(total, confidence="HIGH", buffett=80, deltas=None):
    return {
        "buffett_score": buffett,
        "buffett_breakdown": {
            "profitability": 80,
            "financial_strength": 80,
            "cash_generation": 80,
            "stability": 80,
        },
        "composite_score": {
            "total_score": total,
            "confidence": confidence,
        },
        "dcf_margin_of_safety": 0.25,
        "quality_metrics": {
            "roic_mean": 0.12,
            "revenue_cagr": 0.06,
            "positive_fcf_ratio": 0.8,
            "retained_earnings_positive": True,
        },
        "moat_analysis": {"moat_type": "STRONG", "moat_score": 80},
        "opportunity": None,
        "delta_metrics": deltas or {},
    }


class TestScoreDrop:
    def test_drop_under_threshold_is_none(self):
        assert sell_warning_score_drop(80, 75) is None

    def test_drop_at_threshold_warns(self):
        drop = sell_warning_score_drop(85, 70)
        assert drop is not None and abs(drop - 15) < 1e-9

    def test_no_drop_when_score_rises(self):
        assert sell_warning_score_drop(60, 80) is None


class TestEvaluate:
    def test_buy_signal_emitted_for_strong_company(self):
        analysis = make_analysis(85, buffett=82)
        alerts = evaluate_company("AAPL", analysis)
        types = [a.alert_type for a in alerts]
        assert BUY_SIGNAL in types

    def test_no_buy_for_weak_company(self):
        analysis = make_analysis(45, buffett=30)
        alerts = evaluate_company("AAPL", analysis)
        assert not any(a.alert_type == BUY_SIGNAL for a in alerts)

    def test_sell_warning_on_score_drop(self):
        current = make_analysis(73, buffett=60)
        previous = make_analysis(85, buffett=85)
        alerts = evaluate_company("AAPL", current, previous=previous)
        sell = [a for a in alerts if a.alert_type == SELL_WARNING]
        assert len(sell) == 1
        assert sell[0].confidence == "MEDIUM"

    def test_sell_warning_high_confidence_on_big_drop(self):
        current = make_analysis(50)
        previous = make_analysis(90)
        alerts = evaluate_company("AAPL", current, previous=previous)
        sell = [a for a in alerts if a.alert_type == SELL_WARNING]
        assert sell[0].confidence == "HIGH"

    def test_no_sell_warning_without_previous(self):
        analysis = make_analysis(50)
        alerts = evaluate_company("AAPL", analysis)
        assert not any(a.alert_type == SELL_WARNING for a in alerts)

    def test_trigger_event_on_margin_expansion(self):
        analysis = make_analysis(
            80,
            deltas={
                "gross_margin_delta": 0.03,
                "revenue_growth_delta": 0.01,
                "roic_delta": 0.01,
                "fcf_delta": 0.05,
            },
        )
        assert detect_trigger(analysis) == "MARGIN_EXPANSION"
        alerts = evaluate_company("AAPL", analysis)
        assert any(a.alert_type == TRIGGER_EVENT for a in alerts)

    def test_alert_dict_shape(self):
        alert = Alert(
            ticker="AAPL",
            alert_type=BUY_SIGNAL,
            reason=["test"],
            confidence="HIGH",
        )
        data = alert.to_dict()
        assert data == {
            "ticker": "AAPL",
            "alert_type": BUY_SIGNAL,
            "reason": ["test"],
            "confidence": "HIGH",
        }
        assert to_dicts([alert])[0] == data


class TestRun:
    def test_run_deduplicates_per_type(self):
        analyses = {
            "AAPL": make_analysis(85, buffett=82, deltas={"gross_margin_delta": 0.03}),
            "KO": make_analysis(70, buffett=70, deltas={"roic_delta": 0.03}),
        }
        alerts = run(analyses)
        keys = [(a.ticker, a.alert_type) for a in alerts]
        assert len(keys) == len(set(keys))

    def test_run_with_previous_state(self):
        current = {"AAPL": make_analysis(60, buffett=55)}
        previous = {"AAPL": make_analysis(85, buffett=80)}
        alerts = run(current, previous=previous)
        assert any(a.alert_type == SELL_WARNING for a in alerts)

    def test_run_skips_none_analyses(self):
        # Companies that could not be analyzed (insufficient data) have a
        # None entry; the alert engine must skip them, not crash.
        analyses = {
            "AAPL": make_analysis(85, buffett=82, deltas={"gross_margin_delta": 0.03}),
            "XDATA": None,  # no analysis — regression: used to raise AttributeError
        }
        alerts = run(analyses)
        assert [a.ticker for a in alerts] == ["AAPL"]

    def test_dedupe_first_wins(self):
        alerts = [
            Alert(
                ticker="AAPL",
                alert_type=BUY_SIGNAL,
                reason=["a"],
                confidence="HIGH",
            ),
            Alert(
                ticker="AAPL",
                alert_type=BUY_SIGNAL,
                reason=["b"],
                confidence="HIGH",
            ),
        ]
        unique = dedupe(alerts)
        assert len(unique) == 1
        assert unique[0].reason == ["a"]


class TestNotifier:
    def test_console_notifier_prints(self):
        lines = []

        class Echo:
            def __call__(self, text):
                lines.append(text)

        notifier = ConsoleNotifier(echo=Echo())
        notifier.notify(
            Alert(
                ticker="AAPL",
                alert_type=BUY_SIGNAL,
                reason=["oportunidad"],
                confidence="HIGH",
            )
        )
        assert lines and "AAPL" in lines[0] and "COMPRA" in lines[0]

    def test_notify_all_dispatches(self):
        received = []

        class Fake(Notifier):
            def notify(self, alert):
                received.append(alert.ticker)

        alerts = [
            Alert(ticker=t, alert_type=BUY_SIGNAL, reason=[], confidence="HIGH")
            for t in ("A", "B")
        ]
        notify_all(alerts, [Fake()])
        assert received == ["A", "B"]


class TestRankIntegration:
    def test_rank_score_ranks_analysis(self):
        strong = make_analysis(90)
        weak = make_analysis(40, buffett=30)
        assert rank_score(strong) > rank_score(weak)
        assert rank_score(strong) >= 75.0

    def test_trigger_label_human(self):
        assert trigger_label("MARGIN_EXPANSION") == "expansion de margen bruto"
        assert trigger_label(None) is None
