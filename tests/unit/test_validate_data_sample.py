"""Tests for the recurring data-sample validation script.

Everything here is hermetic: the Financial-DataBase repository and the SEC
EDGAR fetcher are fakes, so no database and no network are touched.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Self

import pytest

from scripts.validate_data_sample import (
    METRICS,
    SecCompanyFactsClient,
    SecConceptClient,
    annual_fact,
    choose_sample,
    compare_metric,
    concept_has_facts,
    format_report,
    load_sp500_universe,
    pct_difference,
    validate_sample,
    write_reports,
)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------
def _concept(
    value: float,
    *,
    form: str = "10-K",
    start: str = "2024-01-01",
    end: str = "2024-12-31",
    filed: str = "2025-02-01",
) -> dict:
    return {
        "units": {
            "USD": [
                {
                    "start": start,
                    "end": end,
                    "val": value,
                    "form": form,
                    "fp": "FY",
                    "filed": filed,
                }
            ]
        }
    }


class FakeRepo:
    """Read-only fake repository whose write methods explode if ever called."""

    def __init__(self, years: dict, financials: dict) -> None:
        self._years = years
        self._financials = financials
        self.read_calls: list[str] = []

    # --- reads ---------------------------------------------------------
    def get_latest_completed_fiscal_year(self, ticker: str):
        self.read_calls.append("get_latest_completed_fiscal_year")
        return self._years.get(ticker)

    def get_fiscal_year_end_date(self, ticker: str, fiscal_year: int):
        self.read_calls.append("get_fiscal_year_end_date")
        return date(2024, 12, 31)

    def get_by_year(self, ticker: str, fiscal_year: int):
        self.read_calls.append("get_by_year")
        return self._financials.get(ticker)

    # --- writes (must never be called) ---------------------------------
    def upsert(self, *args, **kwargs):
        raise AssertionError("validate_data_sample must never write to the DB")

    def upsert_many(self, *args, **kwargs):
        raise AssertionError("validate_data_sample must never write to the DB")

    def delete_ticker(self, *args, **kwargs):
        raise AssertionError("validate_data_sample must never write to the DB")


def _financials(**overrides) -> SimpleNamespace:
    values = {
        "revenue": 100.0,
        "net_income": 10.0,
        "total_assets": 500.0,
        "total_liabilities": 200.0,
        "operating_cash_flow": 50.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------
def test_choose_sample_is_deterministic_for_a_seed():
    universe = [(f"T{i:03d}", f"{i:010d}") for i in range(100)]
    first = choose_sample(universe, 20, 42)
    second = choose_sample(universe, 20, 42)
    assert first == second
    assert len(first) == 20
    assert choose_sample(universe, 20, 7) != first


def test_choose_sample_returns_all_when_size_exceeds_universe():
    universe = [("AAPL", "0000320193")]
    assert choose_sample(universe, 20, 42) == universe


def test_load_sp500_universe_filters_and_sorts(tmp_path):
    csv_path = tmp_path / "universe.csv"
    csv_path.write_text(
        "ticker,cik,company_name,source_index\n"
        "ZZZ,0000000009,Last,SP500\n"
        "AAA,0000000001,First,SP500\n"
        "EUR,0000000002,European,EUROPE\n"
        'BOTH,0000000003,Both,"SP500,NASDAQ100"\n',
        encoding="utf-8",
    )
    assert load_sp500_universe(csv_path) == [
        ("AAA", "0000000001"),
        ("BOTH", "0000000003"),
        ("ZZZ", "0000000009"),
    ]


def test_load_sp500_universe_missing_file_returns_empty(tmp_path):
    assert load_sp500_universe(tmp_path / "nope.csv") == []


# ---------------------------------------------------------------------------
# comparison maths
# ---------------------------------------------------------------------------
def test_pct_difference_relative():
    assert pct_difference(105.0, 100.0) == pytest.approx(5.0)
    assert pct_difference(90.0, 100.0) == pytest.approx(10.0)


def test_pct_difference_skips_missing_or_zero():
    assert pct_difference(None, 100.0) is None
    assert pct_difference(100.0, None) is None
    assert pct_difference(100.0, 0.0) is None


def test_compare_metric_flags_only_above_threshold():
    within = compare_metric(104.0, 100.0, 5.0)
    assert within["skipped"] is False
    assert within["flagged"] is False

    above = compare_metric(106.0, 100.0, 5.0)
    assert above["flagged"] is True
    assert above["diff_pct"] == pytest.approx(6.0)


def test_compare_metric_skips_missing_values():
    check = compare_metric(None, 100.0, 5.0)
    assert check["skipped"] is True
    assert check["flagged"] is False


# ---------------------------------------------------------------------------
# SEC annual-fact extraction
# ---------------------------------------------------------------------------
def test_annual_fact_prefers_full_year_over_quarter():
    payload = {
        "units": {
            "USD": [
                {
                    "start": "2024-01-01",
                    "end": "2024-12-31",
                    "val": 1000,
                    "form": "10-K",
                    "fp": "FY",
                    "filed": "2025-02-01",
                },
                {
                    "start": "2024-10-01",
                    "end": "2024-12-31",
                    "val": 250,
                    "form": "10-K",
                    "fp": "FY",
                    "filed": "2025-02-01",
                },
            ]
        }
    }
    assert annual_fact(payload, date(2024, 12, 31)) == 1000.0


def test_annual_fact_matches_the_fiscal_year_end():
    payload = {
        "units": {
            "USD": [
                {
                    "start": "2023-01-01",
                    "end": "2023-12-31",
                    "val": 900,
                    "form": "10-K",
                    "filed": "2024-02-01",
                },
                {
                    "start": "2024-01-01",
                    "end": "2024-12-31",
                    "val": 1000,
                    "form": "10-K",
                    "filed": "2025-02-01",
                },
            ]
        }
    }
    assert annual_fact(payload, date(2024, 12, 31)) == 1000.0
    assert annual_fact(payload, date(2023, 12, 31)) == 900.0


def test_annual_fact_ignores_non_10k_and_returns_none():
    assert annual_fact({"units": {"USD": [_concept(5.0, form="10-Q")]}}) is None
    assert annual_fact(None) is None
    assert annual_fact({"units": {}}) is None


# ---------------------------------------------------------------------------
# end-to-end validation with fakes
# ---------------------------------------------------------------------------
def _sec_map(**values) -> dict:
    mapping = {}
    for metric, tags in METRICS:
        if metric in values:
            mapping[tags[0]] = _concept(values[metric])
    return mapping


def test_validate_sample_flags_discrepancies_and_builds_report():
    repo = FakeRepo(
        years={"AAA": 2024, "BBB": 2024},
        financials={"AAA": _financials(), "BBB": _financials(revenue=200.0)},
    )
    concepts = {}
    concepts.update(
        {
            ("0000000001", tag): body
            for tag, body in _sec_map(revenue=100.0, net_income=10.0).items()
        }
    )
    concepts.update(
        {("0000000002", tag): body for tag, body in _sec_map(revenue=100.0).items()}
    )
    sec_fetcher = lambda cik, tag: concepts.get((cik, tag))

    report = validate_sample(
        [("AAA", "0000000001"), ("BBB", "0000000002")],
        repo=repo,
        sec_fetcher=sec_fetcher,
        yahoo_fetcher=None,
        seed=42,
        sample_size=2,
    )

    assert report["summary"]["tickers"] == 2
    assert report["summary"]["flagged"] >= 1
    flagged = {(item["ticker"], item["metric"]) for item in report["flagged_fields"]}
    assert ("BBB", "revenue") in flagged
    assert ("AAA", "revenue") not in flagged
    # The report must be JSON-serializable (the .json artifact).
    assert json.loads(json.dumps(report))["summary"]["sec_tickers"] == 2


def test_validate_sample_skips_missing_sec_values_without_flagging():
    repo = FakeRepo(years={"AAA": 2024}, financials={"AAA": _financials()})
    report = validate_sample(
        [("AAA", "0000000001")],
        repo=repo,
        sec_fetcher=lambda cik, tag: None,
        yahoo_fetcher=None,
    )
    assert report["summary"]["flagged"] == 0
    assert report["summary"]["skipped"] == len(METRICS)
    assert report["summary"]["sec_tickers"] == 0


def test_validate_sample_never_writes_to_the_repository():
    repo = FakeRepo(years={"AAA": 2024}, financials={"AAA": _financials()})
    concepts = {
        ("0000000001", tag): body for tag, body in _sec_map(revenue=100.0).items()
    }
    # The fake repo's write methods raise AssertionError if called; the run
    # completing without error is the assertion.
    validate_sample(
        [("AAA", "0000000001")],
        repo=repo,
        sec_fetcher=lambda cik, tag: concepts.get((cik, tag)),
        yahoo_fetcher=None,
    )
    assert all(call.startswith("get_") for call in repo.read_calls)


def test_validate_sample_records_error_for_unknown_ticker():
    repo = FakeRepo(years={}, financials={})
    report = validate_sample(
        [("NOPE", "0000000000")],
        repo=repo,
        sec_fetcher=lambda cik, tag: None,
        yahoo_fetcher=None,
    )
    assert report["tickers"][0]["error"] == "no completed fiscal year"
    assert report["summary"]["no_data"] == 1


# ---------------------------------------------------------------------------
# report writing
# ---------------------------------------------------------------------------
def test_write_reports_writes_log_and_json(tmp_path):
    repo = FakeRepo(years={"AAA": 2024}, financials={"AAA": _financials()})
    report = validate_sample(
        [("AAA", "0000000001")],
        repo=repo,
        sec_fetcher=lambda cik, tag: None,
        yahoo_fetcher=None,
    )
    log_path, json_path = write_reports(report, tmp_path, when=date(2024, 5, 6))
    assert log_path.name == "validation_2024-05-06.log"
    assert json_path.name == "validation_2024-05-06.json"
    assert json_path.exists() and log_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["summary"]["tickers"] == 1
    assert f"Sample: {loaded['sample_size']}" in log_path.read_text(encoding="utf-8")


def test_format_report_marks_flagged_fields():
    report = {
        "generated_at": "2026-01-01T00:00:00Z",
        "sample_size": 1,
        "seed": 42,
        "threshold_pct": 5.0,
        "sources": ["financial_database", "sec_edgar"],
        "tickers": [
            {
                "ticker": "AAA",
                "cik": "0000000001",
                "fiscal_year": 2024,
                "fiscal_year_end": "2024-12-31",
                "error": None,
                "metrics": {
                    "revenue": {
                        "db": 100.0,
                        "ext": 200.0,
                        "diff_pct": 50.0,
                        "flagged": True,
                        "skipped": False,
                        "yahoo": None,
                        "yahoo_diff_pct": None,
                        "yahoo_flagged": False,
                    }
                },
            }
        ],
        "summary": {
            "tickers": 1,
            "compared": 1,
            "skipped": 0,
            "flagged": 1,
            "no_data": 0,
            "sec_tickers": 1,
        },
        "flagged_fields": [
            {
                "ticker": "AAA",
                "metric": "revenue",
                "source": "sec_edgar",
                "db": 100.0,
                "ext": 200.0,
                "diff_pct": 50.0,
            }
        ],
    }
    text = format_report(report)
    assert "<-- FLAGGED" in text
    assert "AAA" in text and "revenue" in text


# ---------------------------------------------------------------------------
# SEC clients
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _opener(body: bytes):
    def open_(request, timeout=None):
        return _FakeResponse(body)

    return open_


def _raising_opener(request, timeout=None):
    raise OSError("network down")


def test_concept_has_facts_distinguishes_an_empty_envelope():
    assert concept_has_facts({"units": {"USD": [{"val": 1.0}]}})
    assert concept_has_facts({"units": {"shares": [{"val": 1.0}]}})
    # The per-tag endpoint answers exactly this for Coca-Cola (2026-10).
    assert not concept_has_facts({"units": {"USD": {}}})
    assert not concept_has_facts({"units": {"USD": []}})
    assert not concept_has_facts({"units": {}})
    assert not concept_has_facts({})
    assert not concept_has_facts(None)


def test_concept_client_fetches_one_tag():
    client = SecConceptClient(
        "agent", min_interval=0.0, opener=_opener(b'{"units": {"USD": [{"val": 1.0}]}}')
    )
    assert client.fetch("320193", "Revenues") == {"units": {"USD": [{"val": 1.0}]}}


def test_concept_client_degrades_every_failure_to_none():
    client = SecConceptClient("agent", min_interval=0.0, opener=_raising_opener)
    assert client.fetch("320193", "Revenues") is None
    malformed = SecConceptClient("agent", min_interval=0.0, opener=_opener(b"not json"))
    assert malformed.fetch("320193", "Revenues") is None


def test_company_facts_client_flattens_a_company_document():
    body = json.dumps(
        {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [{"val": 100.0}]}},
                    "Empty": {"units": {}},
                },
                "dei": {
                    "EntityCommonStockSharesOutstanding": {"units": {"shares": []}}
                },
            }
        }
    ).encode("utf-8")
    client = SecCompanyFactsClient("agent", min_interval=0.0, opener=_opener(body))
    assert client.concepts("320193") == {
        "Revenues": {"units": {"USD": [{"val": 100.0}]}},
        "Empty": {"units": {}},
    }


def test_company_facts_client_degrades_every_failure_to_none():
    client = SecCompanyFactsClient("agent", min_interval=0.0, opener=_raising_opener)
    assert client.concepts("320193") is None
