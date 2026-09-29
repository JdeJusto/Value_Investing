#!/usr/bin/env python3
"""Fetch the current Russell 2000 constituents and write a universe CSV.

Source: the official iShares IWM holdings snapshot
(``.../ishares-russell-2000-etf/latest-holdings.csv``) — IWM holds the full
Russell 2000 index, so the fund's equity positions are the index
constituents (as of the holding date, refreshed by BlackRock usually daily).
Fallback sources (Wikipedia / GitHub mirrors) are not needed because the
fund page exposes a stable CSV download.

CIKs are resolved from the official SEC EDGAR ``company_tickers.json`` map
(ticker → CIK). Companies without an EDGAR CIK (extremely fresh IPOs that
have not yet appeared in the SEC map, or otherwise non-filers) are written
with an empty ``cik``; ``build_universe.py`` drops them from the master
file because fundamentals cannot be sourced for them.

Writes ``config/universe_russell2000.csv`` with columns
``ticker,cik,company_name,source_index`` (``source_index=Russell2000``).
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.universe_common import (  # noqa: E402
    normalize_ticker,
    sec_company_tickers,
    ticker_to_sec,
)

logger = logging.getLogger("fetch_russell2000")

IWM_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239710/"
    "ishares-russell-2000-etf/latest-holdings.csv"
)

# Headers before the actual holdings table (fund metadata + a blank line).
_HEADER_BLOCK_LINES = (
    "Ticker",
    "Name",
    "Sector",
    "Asset Class",
    "Market Value",
    "Weight (%)",
)


def parse_iwm_holdings(text: str) -> list[dict]:
    """Parse the IWM holdings CSV into ``{ticker, name}`` rows.

    Only Equity rows with a non-empty ticker are kept. The asset-class
    column guards against the fund's small non-equity lines (cash, etc.).
    """
    rows: list[dict] = []
    for raw in csv.reader(text.splitlines()):
        if not raw:
            continue
        head = [c.strip() for c in raw]
        if head[0] == "Ticker" and len(head) > 2:
            continue  # the holdings table header row
        first = head[0]
        if first.startswith(("iShares", "Fund Holdings", "Inception",
                             "Shares Outstanding", "Stock", "Bond",
                             "Cash", "Other")):
            continue  # fund metadata block
        if "*" in first and first.count("*") >= 2:
            continue  # iShares placeholder lines ("**..." asterisk rows)
        if len(head) < 4:
            continue
        if head[3].strip().lower() != "equity":
            continue  # only equity holdings represent index constituent
        ticker = normalize_ticker(head[0])
        if not ticker:
            continue
        rows.append({"ticker": ticker, "name": head[1].strip()})
    return rows


def fetch_holdings(url: str = IWM_HOLDINGS_URL) -> str:
    """Download the IWM holdings CSV text (public override point for tests).

    iShares serves the holdings CSV only to a browser-like caller (a plain
    API User-Agent gets a 403) — send a real browser User-Agent plus a
    Referer, matching how the file is served to ordinary users.
    """
    import urllib.request

    browser_ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": browser_ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.ishares.com/us/products/239710/",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def build_universe_russell2000(
    output: str = "config/universe_russell2000.csv",
    holdings_text: str | None = None,
    sec: dict | None = None,
) -> dict:
    """Write the Russell 2000 universe CSV. Returns summary stats."""
    if holdings_text is None:
        holdings_text = fetch_holdings()
    constituents = parse_iwm_holdings(holdings_text)
    if not constituents:
        raise SystemExit("ERROR: no Russell 2000 constituents parsed from IWM holdings")

    sec = sec or sec_company_tickers()
    resolved = 0
    rows: list[dict] = []
    for c in constituents:
        info = ticker_to_sec(c["ticker"], sec)
        cik = info["cik"] if info else ""
        if cik:
            resolved += 1
        rows.append(
            {
                "ticker": c["ticker"],
                "cik": cik,
                "company_name": (info["title"] if info else c["name"]).title(),
                "source_index": "Russell2000",
            }
        )

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "cik", "company_name", "source_index"],
        )
        writer.writeheader()
        writer.writerows(rows)

    return {
        "total": len(rows),
        "resolved_cik": resolved,
        "unresolved_cik": len(rows) - resolved,
        "output": str(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="fetch_russell2000.py")
    parser.add_argument(
        "--output",
        default="config/universe_russell2000.csv",
        help="Output CSV path (default: config/universe_russell2000.csv)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = build_universe_russell2000(args.output)
    print(
        f"Done. {stats['total']} constituents written to {stats['output']} "
        f"(CIK resolved: {stats['resolved_cik']}, unresolved: "
        f"{stats['unresolved_cik']}). Now run scripts/build_universe.py to "
        f"merge this into config/universe.csv."
    )


if __name__ == "__main__":
    main()