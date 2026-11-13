"""`vi filing open/url`: EDGAR URL resolution and browser fallback."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from types import SimpleNamespace

from backend.services.filing_service import filing_edgar_url
from cli.commands import filing


def _record(
    accession="000139718726000127",
    cik="0001397187",
    form="10-Q",
    filed=date(2026, 9, 3),
):
    return SimpleNamespace(
        accession_number=accession,
        cik=cik,
        ticker="LULU",
        form_type=form,
        filing_date=filed,
        sec_url=None,
    )


def test_filing_edgar_url_format():
    assert filing_edgar_url("000139718726000127", "0001397187") == (
        "https://www.sec.gov/Archives/edgar/data/1397187/"
        "000139718726000127/0001397187-26-000127-index.htm"
    )


def test_filing_edgar_url_rejects_missing_values():
    assert filing_edgar_url("", "0001397187") == ""
    assert filing_edgar_url("000139718726000127", "") == ""
    assert filing_edgar_url("short", "0001397187") == ""


def test_has_browser_is_false_in_ssh(monkeypatch):
    monkeypatch.setenv("SSH_CLIENT", "1.2.3.4")
    monkeypatch.setenv("DISPLAY", ":0")
    assert filing._has_browser() is False


def test_has_browser_true_with_display(monkeypatch):
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert filing._has_browser() is True


def test_open_url_prints_when_headless(monkeypatch, capsys):
    monkeypatch.setattr(filing, "_has_browser", lambda: False)
    url = filing_edgar_url("000139718726000127", "0001397187")

    rc = filing._open_url(url)

    assert rc == 0
    out = capsys.readouterr().out
    assert "No browser detected" in out
    assert url in out


def test_open_url_calls_webbrowser(monkeypatch, capsys):
    monkeypatch.setattr(filing, "_has_browser", lambda: True)
    opened: list[str] = []
    monkeypatch.setattr(filing.webbrowser, "open", lambda url: opened.append(url))
    url = filing_edgar_url("000139718726000127", "0001397187")

    rc = filing._open_url(url)

    assert rc == 0
    assert opened == [url]
    assert "Opening:" in capsys.readouterr().out


def test_open_url_only_prints(monkeypatch, capsys):
    url = filing_edgar_url("000139718726000127", "0001397187")
    rc = filing._open_url(url, url_only=True)
    assert rc == 0
    assert capsys.readouterr().out.strip() == url


def test_open_by_accession_resolves_cik(monkeypatch, capsys):
    monkeypatch.setattr(filing, "_has_browser", lambda: False)
    monkeypatch.setattr(
        "backend.services.filing_service.FilingService.get_by_accession",
        lambda self, accession: _record(),
    )

    rc = filing._open(
        Namespace(
            target="0001397187-26-000127",
            index=None,
            all=False,
            url_only=True,
        )
    )

    assert rc == 0
    assert capsys.readouterr().out.strip().endswith("-index.htm")


def test_open_by_ticker_index_uses_default_forms(monkeypatch, capsys):
    calls: dict = {}
    records = [_record(form="10-K"), _record(accession="000139718726000078")]

    monkeypatch.setattr(filing, "_has_browser", lambda: False)

    def _list(self, ticker, **kwargs):
        calls.update({"ticker": ticker, **kwargs})
        return records[: kwargs.get("limit") or len(records)]

    monkeypatch.setattr(
        "backend.services.filing_service.FilingService.list_filings", _list
    )

    rc = filing._url(Namespace(target="LULU", index=2, all=False))

    assert rc == 0
    assert calls["ticker"] == "LULU"
    assert calls["limit"] == 2
    assert calls["form_types"] is not None
    assert "000139718726000078" in capsys.readouterr().out


def test_open_by_ticker_reports_out_of_range(monkeypatch, capsys):
    monkeypatch.setattr(
        "backend.services.filing_service.FilingService.list_filings",
        lambda self, ticker, **kwargs: [_record()],
    )

    rc = filing._url(Namespace(target="LULU", index=5, all=False))

    assert rc == 2
    assert "only 1 filing" in capsys.readouterr().err


def test_unknown_accession_reports_and_exits(monkeypatch, capsys):
    monkeypatch.setattr(
        "backend.services.filing_service.FilingService.get_by_accession",
        lambda self, accession: None,
    )

    rc = filing._url(Namespace(target="000139718726000127", index=None, all=False))

    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_url_command_registration():
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    filing.register(sub)

    args = parser.parse_args(["filing", "url", "LULU", "1"])
    assert args.action == "url"
    assert args.target == "LULU"
    assert args.index == 1
    assert args.func is filing._url
