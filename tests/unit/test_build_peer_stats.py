"""Unit tests for the weekly peer-stats generator (Phase 5A).

The generator is pure above the FDB read: grouping, gating and the artifact
shape are pinned here against synthetic companies, so no database and no
network are involved. Determinism (byte-identical output for the same inputs)
is the headline property — the artifact is consumed by the scorecard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.analytics.peer_stats import (
    MAX_VALUES,
    MIN_GROUP_COMPANIES,
    decimate,
    percentile_rank,
    quantile,
    summarize,
)
from scripts.build_peer_stats import (
    PeerCompany,
    _slugify,
    build_artifacts,
    load_universe,
    metrics_for,
    peer_artifact,
)

GENERATED_AT = "2026-10-15T08:00:00Z"


def company(
    ticker: str,
    *,
    industry: str | None = "Widgets",
    sector: str | None = "Technology",
    pe: float | None = 15.0,
) -> PeerCompany:
    metrics: dict[str, float] = {}
    if pe is not None:
        metrics["pe_ratio"] = pe
    metrics["net_margin"] = 0.10
    return PeerCompany(ticker=ticker, sector=sector, industry=industry, metrics=metrics)


def group(
    count: int, *, industry: str = "Widgets", pe_base: float = 10.0
) -> list[PeerCompany]:
    return [
        company(f"T{index:03d}", industry=industry, pe=pe_base + index)
        for index in range(count)
    ]


# ---------------------------------------------------------------------------
# pure statistics
# ---------------------------------------------------------------------------
def test_quantile_uses_linear_interpolation():
    sample = [float(n) for n in range(1, 11)]  # 1..10
    assert quantile(sample, 0.50) == pytest.approx(5.5)
    assert quantile(sample, 0.10) == pytest.approx(1.9)
    assert quantile(sample, 0.90) == pytest.approx(9.1)


def test_quantile_handles_a_single_value():
    assert quantile([42.0], 0.10) == 42.0
    assert quantile([42.0], 0.90) == 42.0


def test_percentile_rank_counts_ties_half():
    assert percentile_rank([1, 2, 3, 4], 2) == pytest.approx(0.375)
    # A company equal to its group's median reads ~0.5.
    assert percentile_rank([1, 2, 3, 4, 5], 3) == pytest.approx(0.5)
    # Clamped to [0, 1] at both ends.
    assert percentile_rank([1, 2, 3, 4, 5], 100) == 1.0
    assert percentile_rank([1, 2, 3, 4, 5], 0) == 0.0
    assert percentile_rank([], 1) is None


def test_decimate_is_deterministic_and_keeps_both_ends():
    sample = [float(n) for n in range(1000)]
    small = decimate(sample, cap=5)
    assert small == [0.0, 250.0, 500.0, 749.0, 999.0]
    assert small == decimate(sample, cap=5)
    assert decimate(sample, cap=2000) == sample


def test_summarize_reports_the_contract_and_caps_values():
    entry = summarize(range(1, 11))
    assert entry["n"] == 10
    assert entry["min"] == 1.0
    assert entry["max"] == 10.0
    assert entry["median"] == pytest.approx(5.5)
    assert entry["values"] == [float(v) for v in range(1, 11)]
    assert summarize(range(1, 10000))["n"] == 9999
    assert len(summarize(range(1, 10000))["values"]) == MAX_VALUES


def test_summarize_of_an_empty_sample_is_empty():
    assert summarize([]) == {"n": 0, "values": []}


# ---------------------------------------------------------------------------
# slug / universe helpers
# ---------------------------------------------------------------------------
def test_slugify_is_filesystem_safe():
    assert _slugify("Consumer Electronics") == "consumer-electronics"
    assert _slugify("Semiconductors & Equipment") == "semiconductors-equipment"
    assert _slugify("  ") == "unknown"


def test_load_universe_dedupes_and_uppercases(tmp_path: Path):
    path = tmp_path / "u.csv"
    path.write_text(
        "ticker,cik,company_name,source_index\n"
        "aapl,1,Apple,SP500\n"
        "AAPL,1,Apple,SP500\n"
        "msft,2,Microsoft,NASDAQ100\n",
        encoding="utf-8",
    )
    assert load_universe(path) == ["AAPL", "MSFT"]


# ---------------------------------------------------------------------------
# gating: < 10 skipped, exactly 10 written
# ---------------------------------------------------------------------------
def test_groups_below_the_minimum_are_skipped_and_recorded(tmp_path: Path):
    summary = build_artifacts(
        group(MIN_GROUP_COMPANIES - 1),
        generated_at=GENERATED_AT,
        out_dir=tmp_path,
    )
    assert summary["written"] == []
    skipped = [item for item in summary["skipped"] if item["level"] == "industry"]
    assert skipped == [{"level": "industry", "group": "Widgets", "company_count": 9}]
    assert list(tmp_path.glob("industry_*.json")) == []


def test_a_group_of_exactly_the_minimum_is_written(tmp_path: Path):
    summary = build_artifacts(
        group(MIN_GROUP_COMPANIES),
        generated_at=GENERATED_AT,
        out_dir=tmp_path,
    )
    written = [item for item in summary["written"] if item["level"] == "industry"]
    assert len(written) == 1
    assert written[0]["group"] == "Widgets"
    assert written[0]["company_count"] == MIN_GROUP_COMPANIES
    payload = json.loads((tmp_path / "industry_widgets.json").read_text("utf-8"))
    assert payload["company_count"] == MIN_GROUP_COMPANIES


def test_companies_without_metrics_do_not_count_towards_the_gate(tmp_path: Path):
    members = group(MIN_GROUP_COMPANIES)
    members[-1] = PeerCompany(
        ticker="T999", sector="Technology", industry="Widgets", metrics={}
    )
    summary = build_artifacts(members, generated_at=GENERATED_AT, out_dir=tmp_path)
    assert summary["written"] == []


def test_companies_without_a_sector_or_industry_are_dropped(tmp_path: Path):
    members = [
        PeerCompany(ticker=f"T{i}", sector=None, industry=None, metrics={"roe": 0.1})
        for i in range(MIN_GROUP_COMPANIES + 5)
    ]
    summary = build_artifacts(members, generated_at=GENERATED_AT, out_dir=tmp_path)
    assert summary["written"] == []
    assert summary["skipped"] == []


def test_level_filter_writes_one_level_only(tmp_path: Path):
    summary = build_artifacts(
        group(MIN_GROUP_COMPANIES),
        generated_at=GENERATED_AT,
        out_dir=tmp_path,
        levels=("sector",),
    )
    assert {item["level"] for item in summary["written"]} == {"sector"}
    assert (tmp_path / "sector_technology.json").exists()
    assert not (tmp_path / "industry_widgets.json").exists()


# ---------------------------------------------------------------------------
# artifact shape and determinism
# ---------------------------------------------------------------------------
def test_artifact_shape_matches_the_contract():
    payload = peer_artifact("industry", "Widgets", group(12), generated_at=GENERATED_AT)
    assert set(payload) == {
        "level",
        "group",
        "slug",
        "company_count",
        "generated_at",
        "metrics",
    }
    assert payload["level"] == "industry"
    assert payload["group"] == "Widgets"
    assert payload["slug"] == "widgets"
    assert payload["company_count"] == 12
    assert payload["generated_at"] == GENERATED_AT
    entry = payload["metrics"]["pe_ratio"]
    assert set(entry) == {
        "n",
        "min",
        "p10",
        "p25",
        "median",
        "p75",
        "p90",
        "max",
        "values",
        "unit",
    }
    assert entry["unit"] == "multiple"
    assert entry["n"] == 12
    assert entry["values"] == sorted(entry["values"])
    assert payload["metrics"]["net_margin"]["unit"] == "fraction"


def test_artifact_skips_metrics_with_no_values():
    members = [company(f"T{i}", pe=None) for i in range(12)]
    payload = peer_artifact("industry", "Widgets", members, generated_at=GENERATED_AT)
    assert "pe_ratio" not in payload["metrics"]
    assert "net_margin" in payload["metrics"]


def test_build_is_byte_identical_for_the_same_inputs(tmp_path: Path):
    first, second = tmp_path / "a", tmp_path / "b"
    companies = group(12) + group(12, industry="Gadgets", pe_base=30.0)
    build_artifacts(companies, generated_at=GENERATED_AT, out_dir=first)
    build_artifacts(companies, generated_at=GENERATED_AT, out_dir=second)
    files = sorted(path.name for path in first.iterdir())
    assert files == sorted(path.name for path in second.iterdir())
    assert files == [
        "_index.json",
        "industry_gadgets.json",
        "industry_widgets.json",
        "sector_technology.json",
    ]
    for name in files:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_index_records_written_and_skipped(tmp_path: Path):
    companies = group(12) + group(3, industry="Gadgets")
    build_artifacts(companies, generated_at=GENERATED_AT, out_dir=tmp_path)
    index = json.loads((tmp_path / "_index.json").read_text("utf-8"))
    assert index["generated_at"] == GENERATED_AT
    assert [
        item["group"] for item in index["groups"] if item["level"] == "industry"
    ] == ["Widgets"]
    assert [
        item["group"] for item in index["skipped"] if item["level"] == "industry"
    ] == ["Gadgets"]
    # Sector level still qualifies (12 + 3 members share the sector).
    assert any(item["level"] == "sector" for item in index["groups"])


# ---------------------------------------------------------------------------
# metric extraction (scorecard parity)
# ---------------------------------------------------------------------------
def _insight(metric: str, *, series=None, cagr_5y=None):
    from backend.services.financial_insights_service import MetricInsight

    return MetricInsight(
        metric=metric,
        label=metric,
        latest_value="—",
        latest_year=None,
        yoy_change_pct=None,
        cagr_5y=cagr_5y,
        cagr_10y=None,
        average_5y=None,
        trend="stable",
        stability="stable",
        direction_changed=False,
        notes=[],
        kind="ratio",
        series=series or {},
    )


class _Rows:
    """Minimal ``NormalizedFinancials`` stand-in for ``metrics_for``."""

    def __init__(self, equity: float | None = 100.0):
        self.stockholders_equity = equity


def _report(*insights):
    from backend.services.financial_insights_service import InsightsReport

    return InsightsReport(ticker="T", company_name="Test Co", metrics=list(insights))


def test_metrics_for_uses_the_scorecard_analytics():
    report = _report(
        _insight("revenue", series={2020: 100.0, 2025: 200.0}, cagr_5y=14.9),
        _insight("net_margin", series={2025: 0.25}),
        _insight("roe", series={2025: 0.30}),
        _insight("net_income", series={2025: 50.0}),
        _insight("free_cash_flow", series={2025: 20.0}),
    )
    values = metrics_for(report, [_Rows(equity=200.0)], market_cap=1000.0)
    assert values["revenue_cagr_5y"] == pytest.approx(0.149)
    assert values["net_margin"] == pytest.approx(0.25)
    assert values["roe"] == pytest.approx(0.30)
    assert values["pe_ratio"] == pytest.approx(20.0)  # 1000 / 50
    assert values["fcf_yield"] == pytest.approx(0.02)  # 20 / 1000
    assert values["pb_ratio"] == pytest.approx(5.0)  # 1000 / 200


def test_metrics_for_drops_meaningless_multiples():
    report = _report(
        _insight("net_income", series={2025: -10.0}),
        _insight("free_cash_flow", series={2025: -5.0}),
    )
    values = metrics_for(report, [_Rows(equity=-1.0)], market_cap=1000.0)
    assert "pe_ratio" not in values  # loss-making
    assert "pb_ratio" not in values  # negative book value
    assert values["fcf_yield"] == pytest.approx(-0.005)  # negative yields kept


def test_metrics_for_without_prices_keeps_fundamentals():
    report = _report(
        _insight("roe", series={2025: 0.30}),
        _insight("net_income", series={2025: 50.0}),
    )
    values = metrics_for(report, [_Rows()], market_cap=None)
    assert values == {"roe": pytest.approx(0.30)}
