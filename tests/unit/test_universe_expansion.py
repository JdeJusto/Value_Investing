"""Unit tests for the universe-expansion pipeline.

Covers the new scripts (fetch_russell2000.py, fetch_european_indices.py,
build_universe.py, validate_universe_against_fdb.py), the shared SEC
matching helpers (universe_common.py), the prioritized staleness scan
(refresh_service.staleness_ranked) and the daily_workflow named-subset
flags (--universe/--max-refresh/--resume). All network and database access
is mocked or replaced with hermetic fixtures.
"""

from __future__ import annotations

import csv
import datetime as dt

import pandas as pd
import pytest

from scripts.universe_common import (
    SEC_TICKER_PREFERENCES,
    company_key,
    match_sec_company,
    normalize_ticker,
    sec_company_tickers,
    ticker_to_sec,
)


# ---------------------------------------------------------------------------
# universe_common — normalization + SEC matching
# ---------------------------------------------------------------------------
SEC_SAMPLE = {
    "0": {"cik_str": 1000184, "ticker": "SAP", "title": "SAP SE"},
    "1": {"cik_str": 937966, "ticker": "ASML", "title": "ASML HOLDING NV"},
    "2": {"cik_str": 353278, "ticker": "NVO", "title": "NOVO NORDISK A S"},
    "3": {"cik_str": 936340, "ticker": "DTE", "title": "DTE ENERGY CO"},
    "4": {"cik_str": 1306965, "ticker": "SHEL", "title": "Shell plc"},
    "5": {"cik_str": 1091587, "ticker": "ABLZF", "title": "ABB LTD"},
    "6": {"cik_str": 1091587, "ticker": "ABBNY", "title": "ABB LTD"},
    "7": {"cik_str": 67887, "ticker": "MOG-A", "title": "MOOG INC."},
    "8": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "9": {"cik_str": 14693, "ticker": "BF-B", "title": "BROWN FORMAN CORP"},
    "10": {"cik_str": 1851355, "ticker": "TWST", "title": "Twist Bioscience Corp"},
}


@pytest.fixture()
def sec():
    import json as _json

    return sec_company_tickers(raw_json=_json.dumps(SEC_SAMPLE))


class TestNormalizeTicker:
    def test_space_share_class_to_dash(self):
        assert normalize_ticker("MOG A") == "MOG-A"

    def test_dot_to_dash(self):
        assert normalize_ticker("BF.B") == "BF-B"

    def test_lowercase_upcased(self):
        assert normalize_ticker("aapl") == "AAPL"

    def test_empty(self):
        assert normalize_ticker("") == ""


class TestTickerToSec:
    def test_dash_class_share(self, sec):
        info = ticker_to_sec("MOG A", sec)
        assert info["cik"] == "0000067887"
        assert info["ticker"] == "MOG-A"

    def test_exact_ticker(self, sec):
        assert ticker_to_sec("AAPL", sec)["cik"] == "0000320193"

    def test_unknown_returns_none(self, sec):
        assert ticker_to_sec("ZZZZZ", sec) is None


class TestCompanyKey:
    def test_strips_punctuation_and_case(self):
        assert company_key("NOVO NORDISK A/S") == "novonordisk"
        assert company_key("NOVO NORDISK A S") == "novonordisk"

    def test_strips_company_type_tokens(self):
        assert company_key("TotalEnergies SE") == "totalenergies"
        assert company_key("Shell plc") == "shell"

    def test_keeps_distinguishing_tokens(self):
        assert company_key("DTE Energy Co") == "dteenergy"


class TestMatchSecCompany:
    def test_exact_name_match(self, sec):
        info = match_sec_company("Shell plc", sec)
        assert info == {
            "cik": "0001306965",
            "title": "Shell plc",
            "ticker": "SHEL",
            "score": 1.0,
        }

    def test_foreign_domestic_ticker_collision_rejected(self, sec):
        # DAX's DTE is Deutsche Telekom; SEC's DTE is DTE Energy — the name
        # based matcher must NOT conflate them.
        assert match_sec_company("DTE Energy Co", sec) is not None
        assert match_sec_company("Deutsche Telekom AG", sec) is None

    def test_non_filer_returns_none(self, sec):
        assert match_sec_company("Nestlé S.A.", sec) is None
        assert match_sec_company("Siemens AG", sec) is None

    def test_name_variant_last_name(self, sec):
        info = match_sec_company("Novo Nordisk A/S", sec)
        assert info["ticker"] == "NVO"

    def test_otc_ticker_preference_alias(self, sec):
        assert SEC_TICKER_PREFERENCES["ABLZF"] == "ABBNY"
        info = match_sec_company("ABB Ltd", sec)
        assert info["ticker"] == "ABBNY"
        assert info["cik"] == "0001091587"


# ---------------------------------------------------------------------------
# fetch_russell2000 — IWM holdings parsing
# ---------------------------------------------------------------------------
IWM_SAMPLE = """iShares Russell 2000 ETF
Fund Holdings as of,"Sep 21, 2026"
Inception Date,"May 22, 2000"
Shares Outstanding,"265,900,000.00"
Stock,"-"
Bond,"-"
Cash,"-"
Other,"-"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date
"TWST","TWIST BIOSCIENCE","Health Care","Equity","100.00","0.36","100.00","1.00","165.83","United States","NASDAQ","USD","1.00","USD","-"
"MOG A","MOOG INC CLASS A","Industrials","Equity","50.00","0.35","50.00","2.00","369.50","United States","NYSE","USD","1.00","USD","-"
"BRK B","CASH","","Other","1.00","0.00","1.00","1.00","1.00","United States","","USD","1.00","USD","-"
"""


class TestParseIwmHoldings:
    def test_parses_equity_rows_and_skips_metadata(self):
        from scripts.fetch_russell2000 import parse_iwm_holdings

        rows = parse_iwm_holdings(IWM_SAMPLE)
        assert rows == [
            {"ticker": "TWST", "name": "TWIST BIOSCIENCE"},
            {"ticker": "MOG-A", "name": "MOOG INC CLASS A"},
        ]

    def test_share_class_space_becomes_dash(self):
        from scripts.fetch_russell2000 import parse_iwm_holdings

        rows = parse_iwm_holdings(IWM_SAMPLE)
        assert any(r["ticker"] == "MOG-A" for r in rows)


class TestBuildUniverseRussell:
    def test_writes_csv_with_cik_resolution(self, tmp_path, sec):
        from scripts.fetch_russell2000 import build_universe_russell2000

        out = tmp_path / "universe_russell2000.csv"
        stats = build_universe_russell2000(
            output=str(out), holdings_text=IWM_SAMPLE, sec=sec
        )
        assert stats["total"] == 2
        assert stats["resolved_cik"] == 2  # TWST, MOG-A
        text = out.read_text(encoding="utf-8")
        assert "MOG-A,0000067887" in text
        assert "Russell2000" in text


# ---------------------------------------------------------------------------
# fetch_european_indices — table picking + SEC-filing flag
# ---------------------------------------------------------------------------
def _frame(company_names, tickers):
    return pd.DataFrame({"Company": company_names, "Ticker": tickers})


class TestEuropeanConstituents:
    def test_pick_largest_company_table(self):
        from scripts.fetch_european_indices import pick_company_table

        small = pd.DataFrame({"Company": ["A"], "Ticker": ["X"]})
        large = pd.DataFrame(
            {"Company": ["Nestlé", "Roche"], "Ticker": ["NESN", "ROG"]}
        )
        junk = pd.DataFrame({"Year": [2020, 2021], "Level": [1, 2]})
        assert pick_company_table([junk, small, large]) is large

    def test_extract_rows(self):
        from scripts.fetch_european_indices import extract_rows

        df = _frame(["Nestlé", "Roche", "Nestlé"], ["NESN", "ROG", "NESN"])
        assert extract_rows(df) == [
            {"company": "Nestlé", "ticker": "NESN"},
            {"company": "Roche", "ticker": "ROG"},
        ]

    def test_build_flags_sec_filers_and_keeps_domestic_without(self, tmp_path, sec):
        from scripts.fetch_european_indices import build_universe_european

        frames_by_code = {
            "SMI": [_frame(["ABB Ltd", "Nestlé"], ["ABBN", "NESN"])],
        }
        out = tmp_path / "universe_european.csv"
        stats = build_universe_european(
            output=str(out), frames_by_code=frames_by_code, sec=sec
        )
        assert stats["with_sec"] == 1   # ABB (via OTC-preferred ABBNY)
        assert stats["without_sec"] == 1  # Nestlé — not an SEC filer
        text = out.read_text(encoding="utf-8")
        assert "ABBNY," in text and "true" in text
        assert "NESN," in text and "false" in text

    def test_fetch_missing_table_raises(self):
        from scripts.fetch_european_indices import fetch_index_constituents

        with pytest.raises(SystemExit):
            fetch_index_constituents(
                "SMI", frames=[pd.DataFrame({"Year": [1], "Level": [2]})]
            )

    def test_sec_name_collision_excluded(self, tmp_path):
        """A US company sharing the European name must not be flagged as a
        filer of the European company (SEC_NAME_COLLISIONS)."""
        import json as _json

        from scripts.fetch_european_indices import build_universe_european

        # SEC map contains NN, Inc. (US) whose name key collides with
        # "NN Group" after company-type stripping -> a perfect name match
        # that is factually the wrong company.
        sec = sec_company_tickers(
            raw_json=_json.dumps(
                {"0": {"cik_str": 918541, "ticker": "NNBR", "title": "NN INC"}}
            )
        )
        # Under AEX the NN Group collision is curated out -> non-filer row.
        out = tmp_path / "eu.csv"
        stats = build_universe_european(
            output=str(out),
            frames_by_code={"AEX": [_frame(["NN Group"], ["NN.AS"])]},
            sec=sec,
        )
        assert stats["with_sec"] == 0
        assert stats["without_sec"] == 1
        text = out.read_text(encoding="utf-8")
        assert "false" in text and "NNBR" not in text

        # The same name under a different index has no curated collision,
        # so the (imperfect but uncurated) name match still flags a filer.
        stats2 = build_universe_european(
            output=str(tmp_path / "eu2.csv"),
            frames_by_code={"OMXC25": [_frame(["NN Group"], ["NN.CO"])]},
            sec=sec,
        )
        assert stats2["with_sec"] == 1


# ---------------------------------------------------------------------------
# build_universe — merge, dedup, european filter
# ---------------------------------------------------------------------------
def _csv(tmp_path, name, header, rows):
    path = tmp_path / name
    with open(path, "w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    return str(path)


class TestMergeSources:
    def test_dedup_by_ticker_merges_sources(self):
        from scripts.build_universe import merge_sources

        merged = merge_sources(
            [
                [{"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc.", "sources": {"SP500"}}],
                [{"ticker": "aapl", "cik": "0000320193", "name": "", "sources": {"NASDAQ100"}}],
                [{"ticker": "MSFT", "cik": "0000789019", "name": "Microsoft", "sources": {"SP500"}}],
            ]
        )
        assert [m["ticker"] for m in merged] == ["AAPL", "MSFT"]
        assert merged[0]["sources"] == {"SP500", "NASDAQ100"}

    def test_dedup_by_cik_keeps_first_ticker(self):
        from scripts.build_universe import merge_sources

        merged = merge_sources(
            [
                [{"ticker": "GOOGL", "cik": "0001652044", "name": "Alphabet", "sources": {"SP500"}}],
                [{"ticker": "GOOG", "cik": "0001652044", "name": "Alphabet", "sources": {"NASDAQ100"}}],
            ]
        )
        assert [m["ticker"] for m in merged] == ["GOOGL"]
        assert merged[0]["sources"] == {"SP500", "NASDAQ100"}

    def test_rows_without_cik_are_dropped(self):
        from scripts.build_universe import merge_sources

        merged = merge_sources(
            [
                [{"ticker": "X", "cik": "", "name": "no cik", "sources": {"Russell2000"}}],
                [{"ticker": "Y", "cik": "0000000001", "name": "ok", "sources": {"SP500"}}],
            ]
        )
        assert [m["ticker"] for m in merged] == ["Y"]


class TestBuildUniverse:
    def test_master_merge_european_sec_only(self, tmp_path):
        from scripts.build_universe import build_universe

        sp = _csv(
            tmp_path, "universe_sp500_nasdaq.csv",
            ["ticker", "cik", "company_name", "source_index"],
            [{"ticker": "AAPL", "cik": "0000320193", "company_name": "Apple Inc.", "source_index": "SP500"}],
        )
        ru = _csv(
            tmp_path, "universe_russell2000.csv",
            ["ticker", "cik", "company_name", "source_index"],
            [
                {"ticker": "MOGA", "cik": "0000067887", "company_name": "Moog", "source_index": "Russell2000"},
                {"ticker": "NOCIK", "cik": "", "company_name": "No Cik", "source_index": "Russell2000"},
            ],
        )
        eu = _csv(
            tmp_path, "universe_european.csv",
            ["ticker", "cik", "company_name", "source_index", "has_sec_filings"],
            [
                {"ticker": "SHEL", "cik": "0001306965", "company_name": "Shell plc", "source_index": "FTSE100", "has_sec_filings": "true"},
                {"ticker": "NESN", "cik": "", "company_name": "Nestlé", "source_index": "SMI", "has_sec_filings": "false"},
            ],
        )
        out = tmp_path / "master.csv"
        stats = build_universe(
            output=str(out), sp500_file=sp, russell_file=ru, european_file=eu
        )
        assert stats["total"] == 3  # AAPL + MOGA + SHEL (dropped NOCIK, NESN)
        text = out.read_text(encoding="utf-8")
        assert "AAPL" in text and "MOGA" in text and "SHEL" in text
        assert "NESN" not in text and "NOCIK" not in text

    def test_missing_source_raises(self, tmp_path):
        from scripts.build_universe import build_universe

        with pytest.raises(SystemExit):
            build_universe(
                output=str(tmp_path / "m.csv"),
                sp500_file=str(tmp_path / "nope_sp500.csv"),
                russell_file=str(tmp_path / "nope_ru.csv"),
                european_file=str(tmp_path / "nope_eu.csv"),
            )


# ---------------------------------------------------------------------------
# validate_universe_against_fdb — coverage gate
# ---------------------------------------------------------------------------
class FakeRepo:
    def __init__(self, resolvable):
        self.resolvable = set(resolvable)

    def get_cik(self, ticker):
        return ticker if ticker in self.resolvable else None


class TestValidateUniverse:
    def _universe(self, tmp_path, rows):
        path = tmp_path / "u.csv"
        with open(path, "w", encoding="utf-8", newline="") as h:
            w = csv.DictWriter(h, fieldnames=["ticker", "cik", "company_name", "source_index"])
            w.writeheader()
            w.writerows(rows)
        return str(path)

    def test_coverage_passes_above_threshold(self, tmp_path):
        from scripts.validate_universe_against_fdb import validate_universe

        path = self._universe(
            tmp_path,
            [
                {"ticker": "AAPL", "cik": "0000320193", "company_name": "A", "source_index": "SP500"},
                {"ticker": "KO", "cik": "0000021344", "company_name": "K", "source_index": "SP500"},
            ],
        )
        assert validate_universe(path, repo=FakeRepo(["AAPL", "KO"]), threshold=80.0) is True

    def test_coverage_fails_below_threshold(self, tmp_path):
        from scripts.validate_universe_against_fdb import validate_universe

        path = self._universe(
            tmp_path,
            [
                {"ticker": "AAPL", "cik": "0000320193", "company_name": "A", "source_index": "SP500"},
                {"ticker": "NOPE", "cik": "", "company_name": "N", "source_index": "Russell2000"},
            ],
        )
        assert validate_universe(path, repo=FakeRepo(["AAPL"]), threshold=80.0) is False


# ---------------------------------------------------------------------------
# daily_workflow — named universe subsets + parser defaults + staleness
# ---------------------------------------------------------------------------
class TestResolveUniverse:
    def _master(self, tmp_path):
        path = tmp_path / "universe.csv"
        with open(path, "w", encoding="utf-8", newline="") as h:
            w = csv.DictWriter(h, fieldnames=["ticker", "cik", "company_name", "source_index"])
            w.writeheader()
            for row in [
                {"ticker": "AAPL", "cik": "0000320193", "company_name": "A", "source_index": "SP500,NASDAQ100"},
                {"ticker": "KO", "cik": "0000021344", "company_name": "K", "source_index": "SP500"},
                {"ticker": "MOGA", "cik": "0000067887", "company_name": "M", "source_index": "Russell2000"},
                {"ticker": "SHEL", "cik": "0001306965", "company_name": "S", "source_index": "FTSE100"},
                {"ticker": "LEGACY", "cik": "0000000001", "company_name": "L", "source_index": "BOTH"},
            ]:
                w.writerow(row)
        return str(path)

    def test_sp500_default_style_subset(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        tickers = resolve_universe("sp500", self._master(tmp_path))
        assert tickers == ["AAPL", "KO", "LEGACY"]  # BOTH expands to SP500+NASDAQ100

    def test_nasdaq100_includes_both(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        tickers = resolve_universe("nasdaq100", self._master(tmp_path))
        assert tickers == ["AAPL", "LEGACY"]

    def test_russell2000_subset(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        assert resolve_universe("russell2000", self._master(tmp_path)) == ["MOGA"]

    def test_european_subset(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        assert resolve_universe("european", self._master(tmp_path)) == ["SHEL"]

    def test_all_subset(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        assert len(resolve_universe("all", self._master(tmp_path))) == 5

    def test_combined_subset_union(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        tickers = resolve_universe("sp500,nasdaq100", self._master(tmp_path))
        assert tickers == ["AAPL", "KO", "LEGACY"]  # deduped, in file order

    def test_path_spec_falls_back_to_file(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        f = tmp_path / "plain.txt"
        f.write_text("AAPL\nMSFT\n", encoding="utf-8")
        assert resolve_universe(str(f)) == ["AAPL", "MSFT"]

    def test_invalid_named_subset_raises(self, tmp_path):
        from scripts.daily_workflow import resolve_universe

        with pytest.raises(SystemExit):
            resolve_universe("sp500,sp100", self._master(tmp_path))

    def test_parser_defaults_reflect_large_universe_flags(self):
        from scripts.daily_workflow import build_parser

        args = build_parser().parse_args([])
        assert args.universe == "sp500"
        assert args.max_refresh == 200
        assert args.resume is False


class TestStalenessRanked:
    def _service(self, gateway):
        from backend.services.refresh_service import RefreshConfig, RefreshService

        return RefreshService(config=RefreshConfig(), gateway=gateway)

    def _gateway(self, companies, last_synced):
        class G:
            def __init__(self, companies, last_synced):
                self.companies = companies
                self.last_synced = last_synced

            def available(self):
                return True

            def resolve_company(self, ticker):
                return self.companies.get(ticker)

            def last_synced_at(self, company_id):
                return self.last_synced.get(company_id)

        return G(companies, last_synced)

    def test_ranks_most_recent_first_and_never_synced_last(self):
        now = dt.datetime.now(dt.timezone.utc)
        companies = {"A": ("a", "1"), "B": ("b", "2"), "C": ("c", "3")}
        last = {
            "a": now - dt.timedelta(hours=200),
            "b": now - dt.timedelta(hours=180),
            # c never synced (None)
            "c": None,
        }
        service = self._service(self._gateway(companies, last))
        stale, fresh, unknown = service.staleness_ranked(["A", "B", "C"])
        assert stale == ["B", "A", "C"]  # 180h first, 200h next, never-ingested last
        assert fresh == []
        assert unknown == []

    def test_fresh_excluded_and_unknown_kept(self):
        now = dt.datetime.now(dt.timezone.utc)
        companies = {"A": ("a", "1")}
        last = {"a": now - dt.timedelta(hours=10)}  # fresh (< 168h)
        service = self._service(self._gateway(companies, last))
        stale, fresh, unknown = service.staleness_ranked(["A", "NOPE"])
        assert stale == []
        assert fresh == ["A"]
        assert unknown == ["NOPE"]

    def test_check_freshness_still_returns_plain_tuple(self):
        now = dt.datetime.now(dt.timezone.utc)
        companies = {"A": ("a", "1")}
        last = {"a": now - dt.timedelta(hours=200)}
        service = self._service(self._gateway(companies, last))
        stale, fresh, unknown = service.check_freshness(["A"])
        assert stale == ["A"]
        assert fresh == [] and unknown == []


class TestClassifyPriceFailures:
    """Regression: price-failure constants must be resolvable at module scope.

    _classify_price_failures is a module-level helper but previously read the
    PRICE_FAILURE_* constants from an import scoped inside _run(); as soon as
    ANY ticker had no market snapshot the classifier raised
    NameError: PRICE_FAILURE_MAPPING and aborted the workflow. Verify the
    helper returns categorized failures (never raises).
    """

    def _price_service(self, mapping):
        class P:
            def __init__(self, mapping):
                self.mapping = mapping

            def classify_price_failure(self, ticker, known_ticker=None):
                return self.mapping.get(ticker, "unknown")

        return P(mapping)

    def _repo(self, active):
        class R:
            def __init__(self, active):
                self.active = active

            def has_active_listing(self, ticker):
                return self.active.get(ticker)

        return R(active)

    def test_classifies_without_raising(self):
        from scripts.daily_workflow import _classify_price_failures

        price_service = self._price_service({"A": "mapping"})
        repo = self._repo({"A": True, "B": True})
        failures = _classify_price_failures(["A", "B"], price_service, repo)
        assert failures == {"A": "mapping", "B": "unknown"}

    def test_empty_unavailable_returns_empty(self):
        from scripts.daily_workflow import _classify_price_failures

        assert (
            _classify_price_failures([], self._price_service({}), self._repo({}))
            == {}
        )