"""The cross-source data-quality audit: facts, classifier and report.

Everything here is offline and deterministic: the Financial-DataBase side is a
stub repository, the SEC side a stub ``companyconcept`` fetcher and the Yahoo
side a stub fetcher — no network, no database, no clock (``generated_at`` is
injected). The audit only reads; its sole writes are the report files.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from scripts.audit_data_quality import (
    ACTIONS,
    AUDIT_METRICS,
    CSV_COLUMNS,
    DATA_ERROR_EXTERNAL,
    DATA_ERROR_FDB,
    DIFFERENT_PERIOD,
    DIFFERENT_TAG,
    MATCH,
    RESTATEMENT,
    SKIPPED,
    SPLIT_ADJUSTMENT,
    UNCLASSIFIED,
    Fact,
    MetricSpec,
    SecFallbackFetcher,
    annual_facts,
    audit_company,
    build_report,
    classify_comparison,
    format_report,
    load_universe_map,
    metric_value,
    write_reports,
)

FY_START = date(2023, 9, 30)
FY_END = date(2024, 9, 28)


# ---------------------------------------------------------------------------
# fixtures and stubs
# ---------------------------------------------------------------------------
def _annual(
    value: float,
    *,
    end: date = FY_END,
    start: date | None = FY_START,
    form: str = "10-K",
    filed: str = "2024-11-01",
) -> dict:
    """One raw ``companyconcept`` fact (a duration when ``start`` is given)."""
    raw: dict = {"val": value, "end": end.isoformat(), "form": form, "filed": filed}
    if start is not None:
        raw["start"] = start.isoformat()
    return raw


def _concept(*facts: dict, unit: str = "USD") -> dict:
    return {"units": {unit: list(facts)}}


def _sec_fetcher(mapping: dict[str, tuple[str, list[dict]]]):
    """A stubbed ``companyconcept`` client built from ``{tag: (unit, facts)}``."""

    def fetch(cik: str, tag: str) -> dict | None:
        entry = mapping.get(tag)
        if not entry:
            return None
        unit, facts = entry
        return _concept(*facts, unit=unit)

    return fetch


#: Every audited metric, with SEC facts that agree with :func:`_financials`.
_SEC_GOOD: dict[str, tuple[str, list[dict]]] = {
    "Revenues": ("USD", [_annual(100.0)]),
    "NetIncomeLoss": ("USD", [_annual(20.0)]),
    "Assets": ("USD", [_annual(500.0, start=None)]),
    "Liabilities": ("USD", [_annual(200.0, start=None)]),
    "StockholdersEquity": ("USD", [_annual(300.0, start=None)]),
    "NetCashProvidedByUsedInOperatingActivities": ("USD", [_annual(50.0)]),
    "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", [_annual(10.0)]),
    "CommonStockSharesOutstanding": ("shares", [_annual(100.0, start=None)]),
    "EarningsPerShareDiluted": ("USD/shares", [_annual(0.2)]),
    "CommonStockDividendsPerShareDeclared": ("USD/shares", [_annual(0.05)]),
}


def _financials(**overrides) -> SimpleNamespace:
    values = {
        "revenue": 100.0,
        "net_income": 20.0,
        "total_assets": 500.0,
        "total_liabilities": 200.0,
        "stockholders_equity": 300.0,
        "operating_cash_flow": 50.0,
        "capital_expenditure": 10.0,
        "shares_outstanding": 100.0,
        "dividends_paid": 5.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Repo:
    """The read-only slice of the repository the audit is allowed to use."""

    def __init__(self, financials: object | None = None, *, year: int | None = 2024):
        self.financials = _financials() if financials is None else financials
        self.year = year

    def available(self) -> bool:
        return True

    def get_latest_completed_fiscal_year(self, ticker: str) -> int | None:
        return self.year

    def get_by_year(self, ticker: str, year: int) -> object | None:
        return self.financials

    def get_fiscal_year_end_date(self, ticker: str, year: int) -> date | None:
        return FY_END


def _audit(
    sec_fetcher=None,
    *,
    yahoo_fetcher=None,
    split_lookup=None,
    financials=None,
    repo=None,
):
    """Run the audit for one stub company."""
    return audit_company(
        "AAPL",
        "0000320193",
        repo=_Repo(financials) if repo is None else repo,
        sec_fetcher=sec_fetcher,
        yahoo_fetcher=yahoo_fetcher,
        split_lookup=split_lookup,
    )


def _classes(comparisons) -> dict[tuple[str, str], str]:
    return {
        (item["metric"], item["source_b"]): item["classification"]
        for item in comparisons
    }


def _report(**overrides):
    kwargs = {
        "repo": _Repo(),
        "sec_fetcher": _sec_fetcher(_SEC_GOOD),
        "seed": 42,
        "generated_at": "2026-10-17T00:00:00Z",
    }
    kwargs.update(overrides)
    return build_report([("AAPL", "0000320193")], **kwargs)


# ---------------------------------------------------------------------------
# annual facts
# ---------------------------------------------------------------------------
def test_annual_facts_keeps_only_full_year_10k_facts():
    payload = _concept(
        _annual(100.0),
        _annual(40.0, start=date(2024, 6, 30)),  # one quarter, not the year
        _annual(90.0, form="10-Q"),  # an annual span, but not a 10-K
    )
    facts = annual_facts(payload, FY_END)
    assert [fact.value for fact in facts] == [100.0]
    assert facts[0].form == "10-K"


def test_annual_facts_prefers_the_period_closest_to_the_fiscal_year_end():
    payload = _concept(
        _annual(90.0, end=date(2023, 9, 30), start=date(2022, 10, 1)),
        _annual(100.0),
    )
    assert [fact.value for fact in annual_facts(payload, FY_END)] == [100.0, 90.0]


def test_annual_facts_orders_the_latest_filing_first_for_the_same_period():
    payload = _concept(
        _annual(100.0, filed="2024-11-01"),
        _annual(120.0, form="10-K/A", filed="2025-02-01"),
    )
    facts = annual_facts(payload, FY_END)
    assert [fact.value for fact in facts] == [120.0, 100.0]
    assert [fact.filed for fact in facts] == ["2025-02-01", "2024-11-01"]


def test_annual_facts_reads_share_and_per_share_units():
    payload = _concept(_annual(0.2), unit="USD/shares")
    assert annual_facts(payload, FY_END)[0].value == pytest.approx(0.2)


def test_annual_facts_tolerates_a_missing_or_empty_payload():
    assert annual_facts(None, FY_END) == []
    assert annual_facts({}, FY_END) == []
    assert annual_facts({"units": {"USD": []}}, FY_END) == []


# ---------------------------------------------------------------------------
# metric reading
# ---------------------------------------------------------------------------
def test_metric_value_derives_eps_and_dividends_per_share():
    specs = {spec.metric: spec for spec in AUDIT_METRICS}
    payload = _financials(net_income=25.0, dividends_paid=8.0, shares_outstanding=50.0)
    assert metric_value(payload, specs["eps_diluted"]) == pytest.approx(0.5)
    assert metric_value(payload, specs["dividends_per_share"]) == pytest.approx(0.16)


def test_metric_value_returns_none_when_a_derived_input_is_missing_or_zero():
    specs = {spec.metric: spec for spec in AUDIT_METRICS}
    assert metric_value(_financials(net_income=None), specs["eps_diluted"]) is None
    assert metric_value(_financials(shares_outstanding=0), specs["eps_diluted"]) is None


def test_metric_value_reads_a_plain_attribute():
    spec = MetricSpec("revenue", 2.0, ("Revenues",), attribute="revenue")
    assert metric_value(_financials(revenue=42.0), spec) == 42.0
    assert metric_value(_financials(revenue=None), spec) is None


# ---------------------------------------------------------------------------
# classification (pure)
# ---------------------------------------------------------------------------
def test_a_difference_within_tolerance_is_a_match():
    classification, reason = classify_comparison(
        value_a=101.0, value_b=100.0, tolerance_pct=2.0
    )
    assert classification == MATCH
    assert "tolerance" in reason


def test_an_opposite_sign_with_the_same_magnitude_is_a_match():
    classification, reason = classify_comparison(
        value_a=-10.0, value_b=10.0, tolerance_pct=5.0, magnitude_only=True
    )
    assert classification == MATCH
    assert "sign" in reason


def test_an_opposite_sign_is_still_a_difference_without_magnitude_only():
    classification, _ = classify_comparison(
        value_a=-10.0, value_b=10.0, tolerance_pct=5.0
    )
    assert classification == UNCLASSIFIED


def test_a_missing_value_is_skipped_never_a_difference():
    assert (
        classify_comparison(value_a=None, value_b=10.0, tolerance_pct=5.0)[0] == SKIPPED
    )
    assert (
        classify_comparison(value_a=10.0, value_b=None, tolerance_pct=5.0)[0] == SKIPPED
    )


def test_a_strict_metric_with_no_upstream_fact_is_a_financial_database_error():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=None,
        tolerance_pct=2.0,
        authoritative=True,
        upstream_available=False,
        strict=True,
    )
    assert classification == DATA_ERROR_FDB
    assert "no SEC filing" in reason


def test_a_non_strict_metric_with_no_upstream_fact_is_skipped():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=None,
        tolerance_pct=2.0,
        authoritative=True,
        upstream_available=False,
        strict=False,
    )
    assert classification == SKIPPED
    assert "does not tag" in reason


def test_a_period_mismatch_is_reported_as_a_different_period():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=100.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=date(2023, 9, 28),
    )
    assert classification == MATCH  # identical values still match ...

    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=111.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=date(2023, 9, 28),
    )
    assert classification == DIFFERENT_PERIOD
    assert "period ends differ" in reason


def test_a_real_value_under_another_tag_is_a_tag_mismatch():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=111.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=FY_END,
        alternative_tags={
            "RevenueFromContractWithCustomerExcludingAssessedTax": [
                Fact(100.0, period_end=FY_END)
            ]
        },
    )
    assert classification == DIFFERENT_TAG
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in reason


def test_a_superseded_filing_is_a_restatement():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=120.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=FY_END,
        restated=[Fact(100.0, period_end=FY_END, filed="2024-11-01")],
    )
    assert classification == RESTATEMENT
    assert "superseded" in reason


def test_a_split_factor_explains_a_share_count_difference():
    classification, reason = classify_comparison(
        value_a=400.0, value_b=100.0, tolerance_pct=2.0, split_factor=4.0
    )
    assert classification == SPLIT_ADJUSTMENT
    assert "4x" in reason


def test_a_split_factor_is_ignored_for_a_metric_that_does_not_carry_one():
    classification, _ = classify_comparison(
        value_a=400.0, value_b=100.0, tolerance_pct=2.0
    )
    assert classification == UNCLASSIFIED


def test_an_unexplained_difference_is_unclassified():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=150.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=FY_END,
    )
    assert classification == UNCLASSIFIED
    assert "no heuristic" in reason


def test_a_non_authoritative_source_is_blamed_when_the_authority_agrees():
    classification, reason = classify_comparison(
        value_a=100.0,
        value_b=90.0,
        tolerance_pct=5.0,
        authoritative=False,
        authoritative_agrees=True,
    )
    assert classification == DATA_ERROR_EXTERNAL
    assert "authoritative" in reason


def test_a_non_authoritative_source_without_a_reference_is_unclassified():
    classification, _ = classify_comparison(
        value_a=100.0,
        value_b=90.0,
        tolerance_pct=5.0,
        authoritative=False,
        authoritative_agrees=None,
    )
    assert classification == UNCLASSIFIED


def test_period_mismatch_outranks_a_tag_mismatch():
    classification, _ = classify_comparison(
        value_a=100.0,
        value_b=111.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=date(2023, 9, 28),
        alternative_tags={"Revenues": [Fact(100.0, period_end=FY_END)]},
    )
    assert classification == DIFFERENT_PERIOD


# ---------------------------------------------------------------------------
# the driver
# ---------------------------------------------------------------------------
def test_a_company_that_agrees_everywhere_reports_no_discrepancy():
    row = _audit(_sec_fetcher(_SEC_GOOD))
    assert row["error"] is None
    assert len(row["comparisons"]) == len(AUDIT_METRICS)
    assert {item["classification"] for item in row["comparisons"]} == {MATCH}


def test_the_sec_side_flags_a_different_period():
    mapping = dict(_SEC_GOOD)
    mapping["Revenues"] = (
        "USD",
        [_annual(111.0, end=date(2023, 9, 30), start=date(2022, 10, 1))],
    )
    row = _audit(_sec_fetcher(mapping))
    assert _classes(row["comparisons"])[("revenue", "sec_edgar")] == DIFFERENT_PERIOD


def test_the_sec_side_flags_a_different_tag():
    mapping = dict(_SEC_GOOD)
    mapping["Revenues"] = ("USD", [_annual(111.0)])
    mapping["RevenueFromContractWithCustomerExcludingAssessedTax"] = (
        "USD",
        [_annual(100.0)],
    )
    row = _audit(_sec_fetcher(mapping))
    assert _classes(row["comparisons"])[("revenue", "sec_edgar")] == DIFFERENT_TAG


def test_the_sec_side_flags_a_restatement():
    mapping = dict(_SEC_GOOD)
    mapping["Revenues"] = (
        "USD",
        [
            _annual(100.0, filed="2024-11-01"),
            _annual(120.0, form="10-K/A", filed="2025-02-01"),
        ],
    )
    row = _audit(_sec_fetcher(mapping))
    assert _classes(row["comparisons"])[("revenue", "sec_edgar")] == RESTATEMENT


def test_the_sec_side_flags_an_untraceable_strict_metric():
    mapping = dict(_SEC_GOOD)
    del mapping["Revenues"]
    row = _audit(_sec_fetcher(mapping))
    assert _classes(row["comparisons"])[("revenue", "sec_edgar")] == DATA_ERROR_FDB


def test_a_metric_the_filer_does_not_tag_is_skipped_not_flagged():
    mapping = dict(_SEC_GOOD)
    del mapping["CommonStockDividendsPerShareDeclared"]
    row = _audit(_sec_fetcher(mapping))
    assert _classes(row["comparisons"])[("dividends_per_share", "sec_edgar")] == SKIPPED


def test_the_yahoo_side_blames_yahoo_when_sec_confirms_the_database():
    row = _audit(
        _sec_fetcher(_SEC_GOOD),
        yahoo_fetcher=lambda ticker, year, period: ({"revenue": 90.0}, FY_END),
    )
    assert (
        _classes(row["comparisons"])[("revenue", "yahoo_finance")]
        == DATA_ERROR_EXTERNAL
    )


def test_the_yahoo_side_explains_a_split_adjusted_share_count():
    row = _audit(
        _sec_fetcher(_SEC_GOOD),
        yahoo_fetcher=lambda ticker, year, period: (
            {"shares_outstanding": 25.0},
            FY_END,
        ),
        split_lookup=lambda ticker, when: 4.0,
    )
    assert (
        _classes(row["comparisons"])[("shares_outstanding", "yahoo_finance")]
        == SPLIT_ADJUSTMENT
    )


def test_the_yahoo_side_is_skipped_when_yahoo_returns_nothing():
    row = _audit(_sec_fetcher(_SEC_GOOD), yahoo_fetcher=lambda *args: ({}, None))
    assert all(item["source_b"] != "yahoo_finance" for item in row["comparisons"])


def test_a_company_without_fundamentals_is_reported_not_raised():
    row = _audit(repo=_Repo(year=None))
    assert row["error"] == "no completed fiscal year"
    assert row["comparisons"] == []


def test_a_repository_failure_is_recorded_on_the_row():
    class _Broken:
        def get_latest_completed_fiscal_year(self, ticker):
            raise RuntimeError("database down")

    row = _audit(repo=_Broken())
    assert row["error"] == "RuntimeError: database down"


def test_an_unreachable_sec_is_an_outage_not_a_database_defect():
    row = _audit(_sec_fetcher({}))
    assert row["error"] == "SEC EDGAR returned no data"
    assert all(item["source_b"] != "sec_edgar" for item in row["comparisons"])


# ---------------------------------------------------------------------------
# report, outputs
# ---------------------------------------------------------------------------
def test_the_report_summarises_every_comparison():
    report = _report()
    summary = report["summary"]
    assert summary["tickers"] == 1
    assert summary["with_fundamentals"] == 1
    assert summary["errors"] == 0
    assert summary["comparisons"] == len(AUDIT_METRICS)
    assert summary["sec_tickers"] == 1
    assert summary["yahoo_tickers"] == 0
    assert summary["by_classification"] == {MATCH: len(AUDIT_METRICS)}
    assert summary["data_error_fdb"] == 0
    assert report["sample_size"] == 1
    assert report["seed"] == 42
    assert [entry["metric"] for entry in report["metrics"]] == [
        spec.metric for spec in AUDIT_METRICS
    ]


def test_the_report_is_byte_identical_for_the_same_inputs():
    first = json.dumps(_report(), indent=2, sort_keys=True)
    second = json.dumps(_report(), indent=2, sort_keys=True)
    assert first == second


def test_an_untraceable_metric_counts_as_a_financial_database_error():
    mapping = dict(_SEC_GOOD)
    del mapping["Revenues"]
    report = _report(sec_fetcher=_sec_fetcher(mapping))
    assert report["summary"]["data_error_fdb"] == 1
    assert report["summary"]["by_classification"][DATA_ERROR_FDB] == 1
    assert report["summary"]["expected"] == len(AUDIT_METRICS) - 1


def test_write_reports_writes_a_log_a_json_and_a_csv(tmp_path):
    report = _report()
    log_path, json_path, csv_path = write_reports(
        report, tmp_path, when=date(2026, 10, 17)
    )
    assert log_path.name == "audit_data_quality_2026-10-17.log"
    assert json_path.name == "audit_data_quality_2026-10-17.json"
    assert csv_path.name == "audit_data_quality_2026-10-17.csv"
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    assert "Data-quality audit 2026-10-17T00:00:00Z" in log_path.read_text(
        encoding="utf-8"
    )

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(CSV_COLUMNS)
    assert len(rows) == len(AUDIT_METRICS)


def test_the_csv_omits_a_row_that_has_nothing_to_compare(tmp_path):
    mapping = {"Revenues": ("USD", [_annual(100.0)])}
    report = _report(sec_fetcher=_sec_fetcher(mapping))
    _, _, csv_path = write_reports(report, tmp_path, when=date(2026, 10, 17))
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    # A skipped row carries no comparison, so the spreadsheet stays comparable.
    assert SKIPPED not in {row["classification"] for row in rows}
    assert {row["classification"] for row in rows} == {MATCH, DATA_ERROR_FDB}
    assert rows[0]["metric"] == "revenue"


def test_the_log_lists_the_flagged_rows_and_the_summary():
    mapping = dict(_SEC_GOOD)
    del mapping["Revenues"]
    text = format_report(_report(sec_fetcher=_sec_fetcher(mapping)))
    assert "DATA_ERROR_FDB" in text
    assert "investigate and fix" in text
    assert "By classification:" in text
    assert "data_error_fdb=1" in text


def test_the_log_says_so_when_everything_agrees():
    text = format_report(_report())
    assert "all comparisons within tolerance" in text
    assert "data_error_fdb=0" in text


def test_the_log_reports_a_company_level_error():
    text = format_report(_report(repo=_Repo(year=None)))
    assert "ERROR: no completed fiscal year" in text


def test_every_classification_has_a_documented_action():
    for classification in (
        MATCH,
        DIFFERENT_PERIOD,
        DIFFERENT_TAG,
        SPLIT_ADJUSTMENT,
        RESTATEMENT,
        DATA_ERROR_FDB,
        DATA_ERROR_EXTERNAL,
        UNCLASSIFIED,
        SKIPPED,
    ):
        assert ACTIONS[classification]


def test_load_universe_map_reads_tickers_and_ciks(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text(
        "ticker,cik,index\nAAPL,0000320193,SP500\n,,\nMSFT,0000789019,SP500\n",
        encoding="utf-8",
    )
    assert load_universe_map(path) == {"AAPL": "0000320193", "MSFT": "0000789019"}


def test_load_universe_map_tolerates_a_missing_file(tmp_path):
    assert load_universe_map(tmp_path / "nope.csv") == {}


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------
def test_main_rejects_an_unknown_source(capsys):
    from scripts.audit_data_quality import main

    assert main(["--sources", "bogus"]) == 2
    assert "unknown source" in capsys.readouterr().err


def test_main_needs_at_least_one_comparable_source(capsys):
    from scripts.audit_data_quality import main

    assert main(["--sources", "stockanalysis"]) == 2
    assert "no comparable source" in capsys.readouterr().err


def _patch_main(monkeypatch, mapping, tmp_path, *, fetcher=None):
    import scripts.audit_data_quality as audit

    monkeypatch.setenv("SEC_USER_AGENT", "audit-test test@example.com")
    monkeypatch.setattr(
        audit,
        "default_sec_fetcher",
        lambda *args, **kwargs: fetcher or _sec_fetcher(mapping),
    )
    monkeypatch.setattr(
        audit,
        "_resolve_tickers",
        lambda requested, universe: ([("AAPL", "0000320193")], []),
    )
    monkeypatch.setattr(
        "backend.repositories.financial_database_repository.FinancialDatabaseRepository",
        lambda: _Repo(),
    )
    return audit, tmp_path


def test_main_runs_end_to_end_and_returns_zero(monkeypatch, tmp_path, capsys):
    audit, out = _patch_main(monkeypatch, _SEC_GOOD, tmp_path)
    assert audit.main(["--tickers", "AAPL", "--sources", "sec", "--out", str(out)]) == 0
    day = datetime.now(UTC).date().isoformat()
    assert (out / f"audit_data_quality_{day}.json").exists()
    assert (out / f"audit_data_quality_{day}.csv").exists()
    assert (out / f"audit_data_quality_{day}.log").exists()
    assert "Summary: " in capsys.readouterr().out


def test_main_returns_one_when_a_financial_database_error_is_found(
    monkeypatch, tmp_path
):
    mapping = dict(_SEC_GOOD)
    del mapping["Revenues"]
    audit, out = _patch_main(monkeypatch, mapping, tmp_path)
    assert audit.main(["--tickers", "AAPL", "--sources", "sec", "--out", str(out)]) == 1


def test_main_requires_the_sec_user_agent(monkeypatch, tmp_path, capsys):
    import scripts.audit_data_quality as audit

    # ``main`` calls ``load_dotenv``; keep the test independent of the real .env.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setattr(
        "backend.repositories.financial_database_repository.FinancialDatabaseRepository",
        lambda: _Repo(),
    )
    monkeypatch.setattr(
        audit,
        "_resolve_tickers",
        lambda requested, universe: ([("AAPL", "0000320193")], []),
    )
    assert (
        audit.main(["--tickers", "AAPL", "--sources", "sec", "--out", str(tmp_path)])
        == 2
    )
    assert "SEC_USER_AGENT" in capsys.readouterr().err


def test_main_records_that_the_companyfacts_fallback_was_used(
    monkeypatch, tmp_path, capsys
):
    fetcher = SecFallbackFetcher(
        lambda cik, tag: {"units": {"USD": {}}}, lambda cik: _concepts(_SEC_GOOD)
    )
    audit, out = _patch_main(monkeypatch, _SEC_GOOD, tmp_path, fetcher=fetcher)
    assert audit.main(["--tickers", "AAPL", "--sources", "sec", "--out", str(out)]) == 0
    day = datetime.now(UTC).date().isoformat()
    text = (out / f"audit_data_quality_{day}.log").read_text(encoding="utf-8")
    assert "Note: companyconcept returned an empty envelope" in text
    assert "0000320193" in text
    assert "Summary: " in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the SEC endpoints
# ---------------------------------------------------------------------------
def _concepts(mapping: dict[str, tuple[str, list[dict]]]) -> dict[str, dict]:
    """A ``companyfacts``-shaped ``{tag: {"units": ...}}`` document."""
    return {tag: {"units": {unit: facts}} for tag, (unit, facts) in mapping.items()}


def test_an_empty_envelope_switches_the_issuer_to_companyfacts():
    asked: list[str] = []

    def loader(cik: str):
        asked.append(cik)
        return _concepts(_SEC_GOOD)

    fetcher = SecFallbackFetcher(lambda cik, tag: {"units": {"USD": {}}}, loader)
    assert fetcher("0000021344", "Revenues") == {"units": {"USD": [_annual(100.0)]}}
    assert fetcher.fallback_issuers == {"0000021344"}
    # The company document is fetched once, then serves every later tag.
    assert fetcher("0000021344", "Assets") == {
        "units": {"USD": [_annual(500.0, start=None)]}
    }
    assert asked == ["0000021344"]


def test_a_real_envelope_never_triggers_the_fallback():
    def loader(cik: str):  # pragma: no cover - must never run
        raise AssertionError("companyfacts must not be fetched")

    fetcher = SecFallbackFetcher(lambda cik, tag: _concept(_annual(100.0)), loader)
    assert fetcher("0000320193", "Revenues")
    assert fetcher.fallback_issuers == set()


def test_a_failed_fallback_degrades_to_no_data():
    fetcher = SecFallbackFetcher(
        lambda cik, tag: {"units": {"USD": {}}}, lambda cik: None
    )
    assert fetcher("0000021344", "Revenues") is None
    assert fetcher("0000021344", "Assets") is None
    assert fetcher.fallback_issuers == {"0000021344"}


def test_an_issuer_whose_endpoint_is_empty_is_an_outage_not_a_defect():
    row = _audit(lambda cik, tag: {"units": {"USD": {}}})
    assert row["error"] == "SEC EDGAR returned no data"
    assert row["comparisons"] == []


def test_a_tag_retired_years_ago_does_not_mask_a_tag_switch():
    # AAPL stopped filing ``Revenues`` after FY2018; the audited value lives
    # under the ASC 606 tag. Seven years of drift is not a period artifact.
    row = _audit(
        _sec_fetcher(
            {
                "Revenues": (
                    "USD",
                    [_annual(265.0, end=date(2018, 9, 29), start=date(2017, 10, 1))],
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": (
                    "USD",
                    [_annual(100.0)],
                ),
            }
        )
    )
    assert _classes(row["comparisons"])[("revenue", "sec_edgar")] == DIFFERENT_TAG


def test_a_tag_with_the_wrong_period_cannot_explain_the_value():
    row = _audit(
        _sec_fetcher(
            {
                "Revenues": ("USD", [_annual(111.0)]),
                "RevenueFromContractWithCustomerExcludingAssessedTax": (
                    "USD",
                    [_annual(100.0, end=date(2022, 9, 24), start=date(2021, 9, 25))],
                ),
            }
        )
    )
    assert _classes(row["comparisons"])[("revenue", "sec_edgar")] == UNCLASSIFIED


def test_a_period_gap_beyond_the_window_is_not_a_period_artifact():
    classification, _ = classify_comparison(
        value_a=100.0,
        value_b=265.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=date(2018, 9, 29),
    )
    assert classification == UNCLASSIFIED


def test_a_period_gap_inside_the_window_is_expected():
    classification, _ = classify_comparison(
        value_a=100.0,
        value_b=265.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=date(2023, 9, 28),
    )
    assert classification == DIFFERENT_PERIOD


def test_an_alternative_tag_without_a_period_is_still_accepted():
    classification, _ = classify_comparison(
        value_a=100.0,
        value_b=111.0,
        tolerance_pct=2.0,
        period_a=FY_END,
        period_b=date(2018, 9, 29),
        alternative_tags={"SalesRevenueNet": [Fact(100.0)]},
    )
    assert classification == DIFFERENT_TAG
