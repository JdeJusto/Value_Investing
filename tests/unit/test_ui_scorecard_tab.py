"""The Scorecard tab: six dimension cards and their rule tables (text only).

The tab renders ``ScorecardService`` verbatim, so these tests mock the cached
loader (``ui.services.load_scorecard``) with a crafted payload — no FDB, no
Yahoo, no scorecard computation. Demo mode supplies the fundamentals the
analysis page needs before the tabs are built.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"

_MAIN_TABS = [
    "Overview",
    "Methodologies",
    "Scorecard",
    "DCF",
    "Historical",
    "Filings",
    "Financials",
    "Raw",
]

_DIMENSION_LABELS = (
    "Growth",
    "Profitability",
    "Financial Health",
    "Valuation",
    "Shareholder Returns",
    "Management/Moat",
)


def _dimension(
    key: str,
    label: str,
    score: int | None,
    *,
    verdict: str | None = None,
    evaluable: int = 4,
    trend: str = "stable",
) -> dict:
    if verdict is None:
        verdict = (
            "Insufficient"
            if score is None
            else "Strong"
            if score >= 8
            else "Weak"
            if score <= 4
            else "Mixed"
        )
    summary = (
        f"Insufficient data ({evaluable} evaluable rules)."
        if score is None
        else f"{score}/10 — {verdict} ({evaluable} rules)."
    )
    return {
        "key": key,
        "label": label,
        "question": "q",
        "score": score,
        "verdict": verdict,
        "evaluable_rules": evaluable,
        "rules": [
            {
                "rule_id": f"{key}_rule",
                "label": f"{label} rule",
                "status": "PASS" if score is None else "WATCH",
                "value": "12.4%",
                "threshold": "≥ 10%",
                "reason": f"{label} reason.",
                "source_metric": f"{key}.metric",
                "source_methodology": None,
                "source_book": None,
            }
        ],
        "trend": trend,
        "summary": summary,
    }


def _payload(
    *,
    overall: str = "Mixed",
    data_quality: str = "HIGH",
    disagreements: list[str] | None = None,
) -> dict:
    """An AAPL-shaped payload (Growth 7, Valuation 2, ...)."""
    scores = {
        "growth": 7,
        "profitability": 10,
        "financial_health": 8,
        "valuation": 2,
        "shareholder_returns": 10,
        "management_moat": 7,
    }
    return {
        "ticker": "AAPL",
        "company": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "period": "FY",
        "price": 340.0,
        "market_cap": 3.4e12,
        "generated": "",
        "dimensions": [
            _dimension(key, label, scores[key])
            for key, label in zip(
                (
                    "growth",
                    "profitability",
                    "financial_health",
                    "valuation",
                    "shareholder_returns",
                    "management_moat",
                ),
                _DIMENSION_LABELS,
                strict=True,
            )
        ],
        "overall": overall,
        "disagreements": disagreements or [],
        "methodologies": [],
        "data_quality": data_quality,
        "notes": [],
    }


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Demo mode + a clean cache so the mocked loader always wins."""
    monkeypatch.setenv("VI_DEMO", "1")
    streamlit.cache_data.clear()
    yield
    streamlit.cache_data.clear()


def _run(monkeypatch, payload: dict) -> AppTest:
    monkeypatch.setattr(
        "ui.services.load_scorecard", lambda ticker, period="FY": payload
    )
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    return at


def _markdown(at: AppTest) -> list[str]:
    return [element.value for element in at.markdown]


def test_scorecard_tab_sits_between_methodologies_and_dcf(monkeypatch):
    at = _run(monkeypatch, _payload())
    labels = [tab.label for tab in at.tabs if tab.label in _MAIN_TABS]
    assert labels == _MAIN_TABS


def test_six_dimension_cards_render_with_scores(monkeypatch):
    at = _run(monkeypatch, _payload())
    values = _markdown(at)
    for label in _DIMENSION_LABELS:
        assert f"### {label}" in values
    # Exactly six big score marks (one per dimension card).
    score_marks = [value for value in values if re.fullmatch(r"## (?:\d+/10|—)", value)]
    assert len(score_marks) == 6, score_marks
    assert {"## 7/10", "## 10/10", "## 8/10", "## 2/10"} <= set(score_marks)
    joined = " ".join(values)
    assert "**Mixed**" in joined
    assert "**Strong**" in joined
    assert "**Weak**" in joined


def test_rule_table_has_the_expected_columns(monkeypatch):
    at = _run(monkeypatch, _payload())
    expander = next(element for element in at.expander if element.label == "Rules")
    frame = expander.dataframe[0].value
    assert list(frame.columns) == [
        "Status",
        "Rule",
        "Value",
        "Threshold",
        "Why",
        "Source",
    ]
    assert list(frame["Source"]) == ["analytics"]


def test_insufficient_dimension_renders_a_dash_and_does_not_crash(monkeypatch):
    payload = _payload()
    payload["dimensions"][1] = _dimension(
        "profitability", "Profitability", None, evaluable=1
    )
    at = _run(monkeypatch, payload)
    marks = _markdown(at)
    assert "## —" in marks
    assert "**Insufficient** · stable" in marks
    # The card is never hidden or turned into a zero.
    assert "### Profitability" in marks


def test_data_quality_badge_is_rendered(monkeypatch):
    at = _run(monkeypatch, _payload(data_quality="MEDIUM"))
    badge = next(metric for metric in at.metric if metric.label == "Data quality")
    assert badge.value == "MEDIUM"


def test_empty_disagreements_show_no_panel(monkeypatch):
    at = _run(monkeypatch, _payload(disagreements=[]))
    captions = " ".join(caption.value for caption in at.caption)
    assert "read them together" not in captions
    assert not any("is strong" in warning.value for warning in at.warning)


def test_disagreement_panel_names_the_dimensions(monkeypatch):
    message = "Growth is strong (7/10) while Valuation is weak (2/10)."
    at = _run(monkeypatch, _payload(disagreements=[message]))
    warnings = [warning.value for warning in at.warning]
    panel = next((w for w in warnings if "Growth" in w), None)
    assert panel is not None, warnings
    assert "Valuation" in panel
    captions = " ".join(caption.value for caption in at.caption)
    assert "read them together" in captions


def test_financial_company_note_shows_on_thin_coverage(monkeypatch):
    payload = _payload(overall="Mixed")
    payload["dimensions"][5] = _dimension(
        "management_moat", "Management/Moat", 7, evaluable=2
    )
    at = _run(monkeypatch, payload)
    infos = " ".join(info.value for info in at.info)
    assert "Some rules do not apply to this company type" in infos


def test_service_error_is_reported_without_a_traceback(monkeypatch):
    def _boom(ticker, period="FY"):
        raise RuntimeError("database offline")

    monkeypatch.setattr("ui.services.load_scorecard", _boom)
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    assert not at.exception, at.exception
    assert any("database offline" in error.value for error in at.error)


def test_missing_price_renders_dash_and_keeps_the_cards(monkeypatch):
    payload = _payload()
    payload["price"] = None
    at = _run(monkeypatch, payload)
    assert any(metric.value == "—" for metric in at.metric if metric.label == "Price")
    assert any(value == "### Growth" for value in _markdown(at))


def test_missing_scorecard_uses_the_shared_warning(monkeypatch):
    at = _run(monkeypatch, None)
    assert any("returned no data" in error.value for error in at.error) or any(
        "No fundamentals" in warning.value for warning in at.warning
    )
