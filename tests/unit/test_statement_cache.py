"""Parsed-statement JSON cache: write, read, version invalidation, clearing."""

from __future__ import annotations

from datetime import date

from backend.services.financial_statement_parser import (
    PARSER_VERSION,
    FinancialStatementParser,
    StatementType,
    clear_statement_cache,
    load_financial_statement,
    statement_cache_path,
)

HTML = (
    "<html><body><table>"
    "<tr><td></td><td>September 27, 2025</td><td>September 28, 2024</td></tr>"
    "<tr><td>Total assets</td><td>$</td><td>364,980</td><td>$</td><td>352,583</td></tr>"
    "<tr><td>Total liabilities</td><td>$</td><td>308,030</td><td>$</td><td>290,437</td></tr>"
    "</table></body></html>"
)


class _Record:
    ticker = "AAPL"
    cik = "0000320193"
    accession_number = "0000320193-25-000079"
    primary_document = "aapl-20250927.htm"
    form_type = "10-K"
    filing_date = date(2025, 10, 31)
    period_of_report = date(2025, 9, 27)


class _Fetcher:
    def __init__(self):
        self.calls = 0

    def fetch_html(self, *args, **kwargs):
        self.calls += 1
        return HTML


def test_first_call_parses_and_writes_the_json_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    fetcher = _Fetcher()
    statement = load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    assert statement is not None
    assert fetcher.calls == 1
    path = statement_cache_path(
        tmp_path,
        "0000320193",
        "0000320193-25-000079",
        "aapl-20250927.htm",
        StatementType.BALANCE_SHEET,
    )
    assert path.exists()


def test_second_call_reads_the_cache_without_parsing(tmp_path, monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    fetcher = _Fetcher()
    first = load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    assert first is not None

    # A parser that would explode proves the cache short-circuits it.
    class _Boom:
        def parse(self, *args, **kwargs):
            raise AssertionError("the parser must not run on a cache hit")

    monkeypatch.setattr(
        "backend.services.financial_statement_parser.FinancialStatementParser",
        _Boom,
    )
    second = load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    assert second is not None
    assert [line.current for line in second.lines] == [
        line.current for line in first.lines
    ]
    assert fetcher.calls == 1  # the HTML was not re-fetched either


def test_version_mismatch_triggers_a_reparse(tmp_path, monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    fetcher = _Fetcher()
    load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    path = statement_cache_path(
        tmp_path,
        "0000320193",
        "0000320193-25-000079",
        "aapl-20250927.htm",
        StatementType.BALANCE_SHEET,
    )
    payload = path.read_text(encoding="utf-8").replace(
        f'"version": {PARSER_VERSION}', '"version": 0'
    )
    path.write_text(payload, encoding="utf-8")

    parsed: list[int] = []
    original = FinancialStatementParser.parse

    def counting(self, *args, **kwargs):
        parsed.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(FinancialStatementParser, "parse", counting)
    statement = load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    assert statement is not None
    assert parsed, "a stale version must be re-parsed"


def test_statements_have_independent_cache_files(tmp_path, monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    fetcher = _Fetcher()
    load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    income = load_financial_statement(
        _Record(), StatementType.INCOME_STATEMENT, fetcher=fetcher, cache_dir=tmp_path
    )
    assert income is None  # this HTML has no income statement
    files = sorted(path.name for path in tmp_path.rglob("*.json"))
    assert files == ["aapl-20250927.htm.balance_sheet.json"]


def test_clear_cache_removes_json_and_keeps_html(tmp_path, monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    fetcher = _Fetcher()
    load_financial_statement(
        _Record(), StatementType.BALANCE_SHEET, fetcher=fetcher, cache_dir=tmp_path
    )
    html_file = tmp_path / "320193" / "000032019325000079" / "aapl-20250927.htm"
    html_file.parent.mkdir(parents=True, exist_ok=True)
    html_file.write_text(HTML, encoding="utf-8")

    removed = clear_statement_cache(tmp_path)
    assert removed == 1
    assert html_file.exists()
    assert not list(tmp_path.rglob("*.json"))
