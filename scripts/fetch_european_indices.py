#!/usr/bin/env python3
"""Fetch the constituents of the major European equity indices.

Indices sourced from the Wikipedia constituent lists:

  FTSE 100, DAX 40, CAC 40, IBEX 35, FTSE MIB, AEX, SMI,
  OMX Stockholm 30, OMX Copenhagen 20 (labelled OMXC25).

FEASIBILITY: this project derives fundamentals exclusively from SEC EDGAR
(via Financial-DataBase). Only European companies that are SEC filers (ADRs,
20-F / 40-F filers) have fundamentals available. Pure domestic European
companies (the majority of every index) do NOT file with the SEC and are
excluded from the analyzable universe — they are still written to
``config/universe_european.csv`` with ``has_sec_filings=false`` so the
decision is auditable.

Filing status is determined by matching each company name against the
official SEC ``company_tickers.json`` map. Name matching (not ticker
matching) is essential: domestic exchange tickers routinely collide with
unrelated US symbols (DAX ``DTE`` vs DTE Energy).

Output columns: ``ticker,cik,company_name,source_index,has_sec_filings``.
Companies with ``has_sec_filings=true`` carry their US-listed SEC ticker
and CIK; the rest keep their domestic ticker (informational only).
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.universe_common import (  # noqa: E402
    EUROPEAN_INDEXES,
    SEC_USER_AGENT,
    match_sec_company,
    normalize_ticker,
    sec_company_tickers,
)

logger = logging.getLogger("fetch_european_indices")


def _name_column(df) -> Optional[str]:
    lowered = [str(c).strip().lower() for c in df.columns]
    for col, low in zip(df.columns, lowered):
        if low in ("company", "name"):
            return str(col)
    for col, low in zip(df.columns, lowered):
        if "company" in low or low == "name":
            return str(col)
    return None


def _ticker_column(df) -> Optional[str]:
    lowered = [str(c).strip().lower() for c in df.columns]
    for col, low in zip(df.columns, lowered):
        if "ticker" in low or "symbol" in low:
            return str(col)
    for col, low in zip(df.columns, lowered):
        if low == "code":
            return str(col)
    return None


def pick_company_table(frames):
    """The HTML table with a company-name column, a ticker column and the
    most rows (index articles often contain several tables)."""
    best = None
    for df in frames:
        if _name_column(df) is None or _ticker_column(df) is None:
            continue
        n = len(df)
        if best is None or n > best[0]:
            best = (n, df)
    return best[1] if best else None


def extract_rows(df) -> list[dict]:
    """Rows as ``{company, ticker}`` from the picked constituent table."""
    name_col = _name_column(df)
    tick_col = _ticker_column(df)
    rows: list[dict] = []
    seen: set[str] = set()
    for _, cell in df.iterrows():
        name = str(cell[name_col]).strip()
        if not name or name.lower() in ("—", "-", "nan"):
            continue
        ticker = str(cell[tick_col]).strip()
        if ticker.lower() in ("nan", "none", "—", "-"):
            ticker = ""
        key = (ticker.upper(), name.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append({"company": name, "ticker": ticker})
    return rows


def fetch_index_constituents(code: str, frames=None) -> list[dict]:
    """Constituents (``{company, ticker}``) for one European index."""
    if frames is None:
        import pandas as pd

        url, _ = EUROPEAN_INDEXES[code]
        from scripts.universe_common import _http_get_bytes

        html = _http_get_bytes(url, user_agent=SEC_USER_AGENT).decode(
            "utf-8", "replace"
        )
        frames = pd.read_html(io.StringIO(html))
    table = pick_company_table(frames)
    if table is None:
        raise SystemExit(
            f"ERROR: no constituent table found on Wikipedia for {code}. "
            "The article layout may have changed."
        )
    return extract_rows(table)


def build_universe_european(
    output: str = "config/universe_european.csv",
    frames_by_code: Optional[dict] = None,
    sec: Optional[dict] = None,
) -> dict:
    """Write the European universe CSV. Returns summary stats."""
    sec = sec or sec_company_tickers()
    rows: list[dict] = []
    stats: dict[str, dict] = {}
    # When frames are injected (tests/pipeline reuse) only those indices are
    # processed; otherwise every registered index is fetched live.
    codes = sorted(EUROPEAN_INDEXES if frames_by_code is None else frames_by_code)
    for code in codes:
        frames = frames_by_code.get(code) if frames_by_code else None
        constituents = fetch_index_constituents(code, frames=frames)
        filings = non_filings = 0
        for c in constituents:
            info = match_sec_company(c["company"], sec)
            domestic = re.sub(r"\s+", "", c["ticker"].upper())
            if info:
                filings += 1
                rows.append(
                    {
                        "ticker": info["ticker"],
                        "cik": info["cik"],
                        "company_name": info["title"].title(),
                        "source_index": code,
                        "has_sec_filings": "true",
                    }
                )
            else:
                non_filings += 1
                rows.append(
                    {
                        "ticker": normalize_ticker(domestic),
                        "cik": "",
                        "company_name": c["company"],
                        "source_index": code,
                        "has_sec_filings": "false",
                    }
                )
        stats[code] = {"constituents": len(constituents),
                       "with_sec": filings, "without_sec": non_filings}
        logger.info(
            "%s: %d constituents — %d with SEC filings, %d without",
            code, len(constituents), filings, non_filings,
        )

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ticker", "cik", "company_name", "source_index",
                "has_sec_filings",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    with_sec = sum(1 for r in rows if r["has_sec_filings"] == "true")
    return {
        "total": total,
        "with_sec": with_sec,
        "without_sec": total - with_sec,
        "per_index": stats,
        "output": str(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="fetch_european_indices.py")
    parser.add_argument(
        "--output",
        default="config/universe_european.csv",
        help="Output CSV path (default: config/universe_european.csv)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = build_universe_european(args.output)
    print(
        f"Done. {stats['total']} European constituents written to "
        f"{stats['output']}: {stats['with_sec']} with SEC filings "
        f"(analyzable), {stats['without_sec']} without (excluded from the "
        f"master universe). Now run scripts/build_universe.py to merge "
        f"these into config/universe.csv."
    )


if __name__ == "__main__":
    main()