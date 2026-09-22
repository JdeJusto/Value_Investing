#!/usr/bin/env python3
"""Fetch the current S&P 500 and Nasdaq-100 constituent lists.

De-duplicates overlapping tickers and writes ``config/universe_sp500_nasdaq.csv``
with columns ``ticker,cik,company_name,source_index``.  The CIK values and
company names are read from the Financial-DataBase (SEC EDGAR
``company_identifiers`` table) when available.  Tickers not present in
the database — primarily foreign-listed ADRs such as ASML and NVO — are
skipped entirely with a warning.

After running the other fetch scripts (``fetch_russell2000.py``,
``fetch_european_indices.py``), run ``scripts/build_universe.py`` to merge
everything into the master ``config/universe.csv``.

Regenerate after each index-rebalance date (typically quarterly).
"""

from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("fetch_universe")

# FDB depends on the venv and psycopg2; the project root must be on sys.path.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKI_NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
WIKI_NASDAQ100_LIST_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _read_html(url: str) -> list:
    """Fetch a URL as HTML and parse tables via pandas."""
    import io
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    import pandas as pd

    return pd.read_html(io.StringIO(html))


def _wiki_sp500() -> list[str]:
    """Return S&P 500 tickers as a list of strings (BRK.B → BRK-B)."""
    try:
        frames = _read_html(WIKI_SP500_URL)
        if not frames:
            return []
        df = frames[0]
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        tickers = [
            str(t).strip().replace(".", "-") for t in df[col] if str(t).strip()
        ]
        return tickers
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to fetch S&P 500 list from Wikipedia: %s", exc)
        return []


def _wiki_nasdaq100() -> list[str]:
    """Return Nasdaq-100 tickers as a list of strings (BF.B → BF-B).

    The constituents are on the dedicated "List of NASDAQ-100 companies"
    page (the main article renders them via templates that ``pd.read_html``
    cannot parse). We parse the largest table that has a Ticker column and
    fall back to the legacy MediaWiki template regex on the main article.
    """
    import re
    import urllib.request

    try:
        request = urllib.request.Request(
            WIKI_NASDAQ100_LIST_URL, headers={"User-Agent": _USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")

        import io
        import pandas as pd

        frames = pd.read_html(io.StringIO(html))
        best = None
        for df in frames:
            cols = [str(c) for c in df.columns]
            if "Ticker" not in cols:
                continue
            n = len(df)
            if best is None or n > best[0]:
                best = (n, df)
        if best is not None:
            col = "Ticker"
            return sorted(
                {
                    str(v).strip().upper().replace(".", "-")
                    for v in best[1][col]
                    if str(v).strip()
                }
            )

        # Legacy fallback: MediaWiki templates {{NASDAQ|ADBE}} on the main
        # article page.
        request = urllib.request.Request(
            WIKI_NASDAQ100_URL, headers={"User-Agent": _USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")
        tickers = re.findall(
            r"\{\{[Nn][Aa][Ss][Dd][Aa][Qq]\|([A-Za-z0-9\.\-]+)(?:\|[^}]*)?\}\}",
            html,
        )
        if tickers:
            return sorted({t.upper().replace(".", "-") for t in tickers})

        # Ultimate fallback: any table with a 'Symbol'/'Ticker' column.
        frames = pd.read_html(io.StringIO(html))
        for df in frames:
            for col in df.columns:
                if str(col).lower() in ("symbol", "ticker"):
                    return sorted(
                        {
                            str(v).strip().upper().replace(".", "-")
                            for v in df[col]
                            if str(v).strip()
                        }
                    )
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to fetch Nasdaq-100 list from Wikipedia: %s", exc)
        return []


def fetch_universe(output: str = "config/universe_sp500_nasdaq.csv") -> dict:
    """Fetch constituents, resolve CIKs, write ``output``. Returns stats."""
    sp500 = set(_wiki_sp500())
    nasdaq = set(_wiki_nasdaq100())
    all_tickers = sorted(sp500 | nasdaq)

    both = sp500 & nasdaq
    sp500_only = sp500 - nasdaq
    nasdaq_only = nasdaq - sp500

    logger.info(
        "tickers fetched: total=%d  SP500=%d  NASDAQ100=%d  both=%d",
        len(all_tickers),
        len(sp500),
        len(nasdaq),
        len(both),
    )

    # Resolve CIKs from Financial-DataBase.
    repo = _build_repo()
    rows: list[dict] = []
    skipped: list[str] = []
    for ticker in all_tickers:
        name = _resolve_name(repo, ticker)
        cik = _resolve_cik(repo, ticker)
        if cik is None:
            skipped.append(ticker)
            continue
        source = _source_index(ticker, sp500, nasdaq)
        rows.append(
            {"ticker": ticker, "cik": cik, "company_name": name, "source_index": source}
        )

    if skipped:
        logger.warning("skipped %d ticker(s) not in FDB: %s", len(skipped), ", ".join(skipped))

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "cik", "company_name", "source_index"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info("wrote %s (%d rows)", out, len(rows))

    return {
        "total": len(rows),
        "sp500_only": len(sp500_only),
        "nasdaq100_only": len(nasdaq_only),
        "both": len(both),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _build_repo():
    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )
    return FinancialDatabaseRepository()


def _resolve_cik(repo, ticker: str) -> str | None:
    """CIK string or None (skip foreign filers / missing tickers)."""
    try:
        cik = repo.get_cik(ticker)
    except Exception:
        return None
    return cik if cik else None


def _resolve_name(repo, ticker: str) -> str:
    try:
        name = repo.get_company_name(ticker)
    except Exception:
        return ""
    return name or ""


def _source_index(ticker: str, sp500: set, nasdaq: set) -> str:
    in_sp = ticker in sp500
    in_nq = ticker in nasdaq
    if in_sp and in_nq:
        return "BOTH"
    if in_sp:
        return "SP500"
    return "NASDAQ100"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = fetch_universe()
    print(
        f"Done. {stats['total']} tickers written.  "
        f"SP500-only: {stats['sp500_only']} | "
        f"NASDAQ100-only: {stats['nasdaq100_only']} | "
        f"Both: {stats['both']} | "
        f"Skipped (no CIK): {stats['skipped_count']}"
    )
    print(
        "Now run scripts/fetch_russell2000.py + scripts/fetch_european_indices.py, "
        "then scripts/build_universe.py to merge all indices into config/universe.csv."
    )
