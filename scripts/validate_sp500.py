#!/usr/bin/env python3
"""S&P 500 data validation pipeline for Value Investing.

Steps (each produces a file under data/):

  constituents  -> data/sp500_constituents.csv
  sample        -> data/validation_sample_200.csv         (fixed seed)
  vi            -> data/validation_value_investing_200.csv
  external      -> data/validation_external_200.csv
  compare       -> data/validation_discrepancies_200.csv
  all           -> run sample..compare (constituents assumed built)

Run from the repository root, e.g.:

  python -m scripts.validate_sp500 all --seed 42 --limit 200

Use --limit N to run on a subset for a smoke test.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import random
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"

CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "main/data/constituents.csv"
)

# Normalize dataset symbols that use '.' to the Yahoo/VI convention (dash).
SYMBOL_FIXES = {"BRK.B": "BRK-B", "BF.B": "BF-B"}

# Metric definitions used by the comparison step.
#  - kind 'pct': flag when |vi - ext| / |ext| (in %) exceeds the threshold.
#  - kind 'pp' : flag when the absolute percentage-point difference
#                (vi - ext) * 100 exceeds the threshold (metrics stored as
#                decimal fractions, e.g. 0.0125 == 1.25%).
METRICS = [
    ("revenue", "pct", 2.0),
    ("net_income", "pct", 5.0),
    ("total_assets", "pct", 2.0),
    ("total_liabilities", "pct", 2.0),
    ("operating_cash_flow", "pct", 5.0),
    ("eps", "pct", 5.0),
    ("pe_ratio", "pct", 10.0),
    ("fcf_yield", "pp", 0.5),
    ("roe", "pct", 10.0),
    ("net_margin", "pp", 2.0),
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Step 1: constituents
# ---------------------------------------------------------------------------
def build_constituents(out: Path, verbose: bool = False) -> None:
    """Fetch the S&P 500 list and enrich each row with the Financial-DataBase
    company id + CIK so tickers map to the same EDGAR records we validate."""
    with urllib.request.urlopen(CONSTITUENTS_URL, timeout=60) as resp:
        text = resp.read().decode("utf-8")

    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )

    repo = FinancialDatabaseRepository()
    rows = list(csv.DictReader(io.StringIO(text)))

    def _normalize(symbol: str) -> str:
        symbol = symbol.strip().upper()
        return SYMBOL_FIXES.get(symbol, symbol)

    out_rows = []
    missing_ticker = 0
    for r in rows:
        symbol = _normalize(r["Symbol"])
        cik = r.get("CIK") or ""
        if cik:
            cik = cik.strip().zfill(10)
        company_id = repo._get_company_id_by_ticker(symbol)
        if not company_id:
            missing_ticker += 1
            if verbose:
                print(f"  no DB ticker: {symbol}")
        out_rows.append(
            {
                "ticker": symbol,
                "company_name": r["Security"].strip(),
                "cik": cik,
                "sector": (r.get("GICS Sector") or "").strip(),
                "in_database": "yes" if company_id else "no",
            }
        )

    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["ticker", "company_name", "cik", "sector", "in_database"]
        )
        writer.writeheader()
        writer.writerows(out_rows)

    total = len(out_rows)
    in_db = sum(1 for r in out_rows if r["in_database"] == "yes")
    print(
        f"  S&P 500: {total} symbols "
        f"(unique CIKs {len({r['cik'] for r in out_rows if r['cik']})}), "
        f"{in_db} present in Financial-DataBase ({missing_ticker} missing)"
    )


# ---------------------------------------------------------------------------
# Step 2: random sample
# ---------------------------------------------------------------------------
def build_sample(out: Path, seed: int, limit: int | None) -> None:
    """Select a seeded random sample of 200 unique S&P 500 companies (by CIK)."""
    const = _read_csv(DATA_DIR / "sp500_constituents.csv")
    by_cik: dict[str, dict] = {}
    for r in const:
        if r["cik"]:
            by_cik.setdefault(r["cik"], r)
    companies = sorted(by_cik.values(), key=lambda r: r["ticker"])

    rng = random.Random(seed)
    companies = rng.sample(companies, len(companies))  # shuffle deterministically
    cap = limit if limit is not None and 0 < limit < len(companies) else 200
    chosen = companies[:cap]

    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["ticker", "cik", "company_name", "sector"]
        )
        writer.writeheader()
        for r in chosen:
            writer.writerow(
                {
                    "ticker": r["ticker"],
                    "cik": r["cik"],
                    "company_name": r["company_name"],
                    "sector": r["sector"],
                }
            )

    print(f"  sampled {len(chosen)} companies (seed={seed})")


# ---------------------------------------------------------------------------
# Step 3: Value Investing metrics
# ---------------------------------------------------------------------------
def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    try:
        den = float(den)
    except (TypeError, ValueError):
        return None
    if den == 0:
        return None
    return num / den


def vi_metrics_for(repo, price_service, ticker: str, target_fy: int | None = None) -> dict[str, Any]:
    """Compute the validation metrics the way Value Investing does:
    fundamentals from Financial-DataBase (latest completed fiscal year, or the
    explicitly requested year) and real-time price/shares from PriceService
    (never persisted)."""
    row: dict[str, Any] = {
        "ticker": ticker,
        "fiscal_year": None,
        "ok": False,
        "error": None,
    }
    try:
        fy = target_fy or repo.get_latest_completed_fiscal_year(ticker)
        if fy is None:
            row["error"] = "no completed fiscal year"
            return row
        fin = repo.get_by_year(ticker, fy)
        if fin is None:
            row["error"] = "no fundamentals"
            return row

        price = price_service.get_current_price(ticker)
        current_shares = price_service.get_shares_outstanding(ticker)
        diluted_shares = repo.get_shares_outstanding(ticker, fy, prefer_diluted=True)

        fcf = fin.free_cash_flow
        if (
            fcf is None
            and fin.operating_cash_flow is not None
            and fin.capital_expenditure is not None
        ):
            fcf = fin.operating_cash_flow - fin.capital_expenditure

        market_cap = price * float(current_shares) if price and current_shares else None

        # As-reported diluted EPS pairs the *diluted* available-to-common net
        # income with the diluted share count (they differ when assumed
        # conversions of LLC units / dilutive securities reallocate income,
        # e.g. Carvana 2025: 1,895M / 224.3M = 8.45). Fall back to the basic
        # available-to-common net income when the diluted one is not filed.
        diluted_ni = repo.get_available_to_common_diluted_net_income(ticker, fy)
        eps_num = diluted_ni if diluted_ni is not None else fin.net_income
        eps = _safe_div(eps_num, diluted_shares)
        row.update(
            {
                "fiscal_year": fy,
                "fiscal_year_end": str(repo.get_fiscal_year_end_date(ticker, fy) or ""),
                "price": price,
                "market_cap": market_cap,
                "revenue": fin.revenue,
                "net_income": fin.net_income,
                "total_assets": fin.total_assets,
                "total_liabilities": fin.total_liabilities,
                "operating_cash_flow": fin.operating_cash_flow,
                "capital_expenditure": fin.capital_expenditure,
                "free_cash_flow": fcf,
                "shares_fy": diluted_shares,
                "shares_current": current_shares,
                "stockholders_equity": fin.stockholders_equity,
                "eps": eps,
                "pe_ratio": _safe_div(price, eps),
                "fcf_yield": _safe_div(fcf, market_cap),
                "roe": _safe_div(fin.net_income, fin.stockholders_equity),
                "net_margin": _safe_div(fin.net_income, fin.revenue),
                "ok": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def build_vi_metrics(out: Path, limit: int | None) -> None:
    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )
    from backend.services.price_service import get_price_service

    sample = _read_csv(DATA_DIR / "validation_sample_200.csv")
    if limit:
        sample = sample[:limit]

    repo = FinancialDatabaseRepository()
    price_service = get_price_service()

    rows = []
    for i, r in enumerate(sample, 1):
        ticker = r["ticker"]
        start = time.time()
        rows.append(vi_metrics_for(repo, price_service, ticker))
        print(f"  [{i}/{len(sample)}] {ticker} ({time.time()-start:.1f}s)")
        sys.stdout.flush()

    _write_metrics(out, rows)
    ok = sum(1 for x in rows if x["ok"])
    print(f"  wrote {len(rows)} rows to {out} ({ok} ok, {len(rows)-ok} failed)")


# ---------------------------------------------------------------------------
# Step 4: external metrics (Yahoo Finance)
# ---------------------------------------------------------------------------
def ext_metrics_for(
    provider, ticker: str, target_fye: str | None = None
) -> dict[str, Any]:
    """Compute the same metrics from Yahoo Finance (independent source).

    ``target_fye`` anchors the fiscal period: the Value Investing side labels
    years by the 10-K report year while Yahoo labels by the calendar year of
    the fiscal period end, so the comparison is done on the fiscal period-end
    date."""
    row: dict[str, Any] = {"ticker": ticker, "ok": False, "error": None}
    try:
        entries = provider.get_fiscal_year_end_dates(ticker)
        idx = 0
        if target_fye:
            try:
                target = date.fromisoformat(target_fye[:10])
            except ValueError:
                target = None
            if target:
                for i, entry in enumerate(entries):
                    try:
                        end_date = date.fromisoformat(str(entry["end_date"])[:10])
                    except ValueError:
                        continue
                    if abs((end_date - target).days) <= 7:
                        idx = i
                        break

        fin = provider.get_financials(ticker, idx)
        if fin is None:
            row["error"] = "no yahoo financials"
            return row
        price = provider.get_current_price(ticker)
        shares = provider.get_shares_outstanding(ticker)
        market_cap = price * float(shares) if price and shares else None

        fcf = fin.free_cash_flow
        if (
            fcf is None
            and fin.operating_cash_flow is not None
            and fin.capital_expenditure is not None
        ):
            fcf = fin.operating_cash_flow - fin.capital_expenditure

        fiscal_year_end = ""
        if entries and idx < len(entries):
            fiscal_year_end = str(entries[idx]["end_date"])[:10]

        row.update(
            {
                "fiscal_year": fin.fiscal_year,
                "fiscal_year_end": fiscal_year_end,
                "price": price,
                "market_cap": market_cap,
                "revenue": fin.revenue,
                "net_income": fin.net_income,
                "total_assets": fin.total_assets,
                "total_liabilities": fin.total_liabilities,
                "operating_cash_flow": fin.operating_cash_flow,
                "capital_expenditure": fin.capital_expenditure,
                "free_cash_flow": fcf,
                "shares_current": shares,
                "stockholders_equity": fin.shareholders_equity,
                "eps": fin.diluted_eps,
                "pe_ratio": _safe_div(price, fin.diluted_eps),
                "fcf_yield": _safe_div(fcf, market_cap),
                "roe": _safe_div(fin.net_income, fin.shareholders_equity),
                "net_margin": _safe_div(fin.net_income, fin.revenue),
                "ok": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def build_external_metrics(out: Path, limit: int | None) -> None:
    from backend.providers.yahoo.provider import YahooFinanceProvider

    sample = _read_csv(DATA_DIR / "validation_sample_200.csv")
    if limit:
        sample = sample[:limit]

    # Anchor the external fiscal period on the fiscal period-end of the Value
    # Investing side (the latest completed fiscal year), not on the year label.
    vi_rows = _read_csv(DATA_DIR / "validation_value_investing_200.csv")
    vi_fye = {r["ticker"]: r.get("fiscal_year_end") for r in vi_rows}

    provider = YahooFinanceProvider()
    rows = []
    for i, r in enumerate(sample, 1):
        ticker = r["ticker"]
        start = time.time()
        rows.append(ext_metrics_for(provider, ticker, target_fye=vi_fye.get(ticker)))
        print(f"  [{i}/{len(sample)}] {ticker} ({time.time()-start:.1f}s)")
        sys.stdout.flush()

    _write_metrics(out, rows)
    ok = sum(1 for x in rows if x["ok"])
    print(f"  wrote {len(rows)} rows to {out} ({ok} ok, {len(rows)-ok} failed)")


# ---------------------------------------------------------------------------
# Step 5: comparison
# ---------------------------------------------------------------------------
def _severity(ratio: float) -> str:
    """ratio = observed threshold multiple (>=1 means flagged)."""
    if ratio >= 5.0:
        return "HIGH"
    if ratio >= 2.0:
        return "MEDIUM"
    return "LOW"


FYE_TOLERANCE_DAYS = 7


def compare_rows(vi_row: dict, ext_row: dict) -> list[dict[str, Any]]:
    """Compare a single (vi, external) pair; returns flagged discrepancy rows.

    Percent metrics use |vi - ext| / |ext| (in %). Percentage-point metrics
    (fcf_yield, net_margin, stored as decimal fractions) are compared by their
    difference in percentage points.
    """
    flagged: list[dict[str, Any]] = []
    vi_fye = str(vi_row.get("fiscal_year_end") or "")
    ext_fye = str(ext_row.get("fiscal_year_end") or "")
    fiscal_period_mismatch = False
    if vi_fye and ext_fye:
        try:
            vi_date = date.fromisoformat(vi_fye[:10])
            ext_date = date.fromisoformat(ext_fye[:10])
            fiscal_period_mismatch = abs((ext_date - vi_date).days) > FYE_TOLERANCE_DAYS
        except ValueError:
            fiscal_period_mismatch = vi_fye != ext_fye
    if fiscal_period_mismatch:
        flagged.append(
            {
                "ticker": vi_row.get("ticker"),
                "metric": "fiscal_year",
                "value_investing": vi_row.get("fiscal_year"),
                "external_source": ext_row.get("fiscal_year"),
                "abs_diff": None,
                "pct_diff": None,
                "severity": "HIGH",
            }
        )
    for metric, kind, threshold in METRICS:
        va, vb = vi_row.get(metric), ext_row.get(metric)
        if va is None or vb is None or va == "" or vb == "":
            continue
        try:
            va_f, vb_f = float(va), float(vb)
        except (TypeError, ValueError):
            continue
        if math.isnan(va_f) or math.isnan(vb_f):
            continue
        if kind == "pct":
            if vb_f == 0:
                if va_f != 0:
                    flagged.append(
                        {
                            "ticker": vi_row.get("ticker"),
                            "metric": metric,
                            "value_investing": va_f,
                            "external_source": vb_f,
                            "abs_diff": None,
                            "pct_diff": None,
                            "severity": "HIGH",
                        }
                    )
                continue
            pct = (va_f - vb_f) / abs(vb_f) * 100.0
            if abs(pct) > threshold:
                flagged.append(
                    {
                        "ticker": vi_row.get("ticker"),
                        "metric": metric,
                        "value_investing": round(va_f, 4),
                        "external_source": round(vb_f, 4),
                        "abs_diff": round(va_f - vb_f, 4),
                        "pct_diff": round(pct, 2),
                        "severity": _severity(abs(pct) / threshold),
                    }
                )
        else:  # percentage points
            pp = (va_f - vb_f) * 100.0
            if abs(pp) > threshold:
                flagged.append(
                    {
                        "ticker": vi_row.get("ticker"),
                        "metric": metric,
                        "value_investing": round(va_f, 5),
                        "external_source": round(vb_f, 5),
                        "abs_diff": round(pp, 3),
                        "pct_diff": None,
                        "severity": _severity(abs(pp) / threshold),
                    }
                )
    return flagged


def build_discrepancies(out: Path) -> None:
    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )
    from backend.services.price_service import get_price_service

    vi_rows = _read_csv(DATA_DIR / "validation_value_investing_200.csv")
    ext_rows = _read_csv(DATA_DIR / "validation_external_200.csv")

    vi = {r["ticker"]: r for r in vi_rows if r.get("ok", "") == "True"}
    ext = {r["ticker"]: r for r in ext_rows if r.get("ok", "") == "True"}

    # Safety net: when the external side could not anchor on the Value Investing
    # fiscal period-end (period missing on the external side), re-fetch the
    # Value Investing metrics on the DB fiscal year that shares the period, so
    # both sides still describe the same fiscal period.
    repo = FinancialDatabaseRepository()
    price_service = get_price_service()
    for ticker in set(vi) & set(ext):
        vi_fye = str(vi[ticker].get("fiscal_year_end") or "")
        ext_fye = str(ext[ticker].get("fiscal_year_end") or "")
        if not (vi_fye and ext_fye) or vi_fye == ext_fye:
            continue
        db_year = _db_year_for_fye(repo, ticker, ext_fye)
        if db_year is None:
            continue
        synced = vi_metrics_for(repo, price_service, ticker, target_fy=db_year)
        if synced.get("ok") and str(synced.get("fiscal_year_end") or "") == ext_fye:
            vi[ticker] = synced

    flagged: list[dict[str, Any]] = []
    compared = 0
    for ticker in sorted(set(vi) & set(ext)):
        compared += 1
        flagged.extend(compare_rows(vi[ticker], ext[ticker]))

    # Apply configured exclusions (config/validation_exclusions.yaml): rows
    # that match an exclusion rule are marked EXCLUDED and counted separately,
    # so genuinely unexplained discrepancies stay easy to see.
    rules = _load_exclusions(PROJECT_ROOT / "config" / "validation_exclusions.yaml")
    excluded_by_severity: dict[str, int] = {}
    flagged_out: list[dict[str, Any]] = []
    for row in flagged:
        orig = row["severity"]
        rule = _match_exclusion(row, rules)
        if rule is not None:
            excluded_by_severity[orig] = excluded_by_severity.get(orig, 0) + 1
            row["severity"] = "EXCLUDED"
            row["classification"] = rule.get("classification", "")
            row["exclusion_reason"] = rule.get("reason", "")
        else:
            row["classification"] = ""
            row["exclusion_reason"] = ""
        flagged_out.append(row)
    flagged = flagged_out

    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ticker",
                "metric",
                "value_investing",
                "external_source",
                "abs_diff",
                "pct_diff",
                "severity",
                "classification",
                "exclusion_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(flagged)

    print(f"  compared {compared} companies; wrote {len(flagged)} discrepancy rows")
    _summarize(flagged, compared, excluded_by_severity)


def _load_exclusions(path: Path) -> list[dict[str, str]]:
    """Parse the minimal YAML-subset used by config/validation_exclusions.yaml.

    The file has a single top-level key ``validation_exclusions`` whose value is
    a list of blocks.  Each block starts with ``- ticker:`` and contains scalar
    ``key: value`` fields.  ``#`` comments and single/double quoted values are
    stripped.  No PyYAML dependency is required.
    """
    rules: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    if not path.exists():
        return rules
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.split("#", 1)[0]
        indent = len(stripped) - len(stripped.lstrip(" \t"))
        line = stripped.strip()
        if not line:
            continue
        # Block start: a "- " item begins a new rule
        if line.startswith("- "):
            if current is not None:
                rules.append(current)
            current = {}
            line = line[2:]
        elif indent == 0:
            # Top-level key (e.g. "validation_exclusions:") — reset context
            current = None
            continue
        if current is not None and ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip().strip("'\"")
    if current is not None:
        rules.append(current)
    return rules


def _match_exclusion(
    row: dict[str, Any], rules: list[dict[str, str]]
) -> dict[str, str] | None:
    """Return the first matching rule for (ticker, metric), or None.

    A rule matches when its ``ticker`` and ``metric`` fields equal the row's
    ticker and metric.  The special metric value ``*`` matches any metric.
    """
    ticker = row.get("ticker", "")
    metric = row.get("metric", "")
    for rule in rules:
        rule_ticker = rule.get("ticker", "")
        rule_metric = rule.get("metric", "")
        if not rule_ticker or not rule_metric:
            continue
        if rule_ticker == ticker and rule_metric in (metric, "*"):
            return rule
    return None


def _db_year_for_fye(repo, ticker: str, fye: str) -> int | None:
    """Return the DB fiscal_year whose fiscal period-end matches ``fye``."""
    try:
        target = date.fromisoformat(fye[:10])
    except ValueError:
        return None
    for fy in repo.list_years(ticker):
        fy_end = repo.get_fiscal_year_end_date(ticker, fy.fiscal_year)
        if fy_end is None:
            continue
        if abs((fy_end - target).days) <= 7:
            return fy.fiscal_year
    return None


def _summarize(
    flagged: list[dict],
    compared: int,
    excluded_by_severity: dict[str, int] | None = None,
) -> None:
    from collections import Counter

    by_metric = Counter(r["metric"] for r in flagged)
    by_sev = Counter(r["severity"] for r in flagged)
    total = len(flagged)
    sum(excluded_by_severity.values()) if excluded_by_severity else 0
    n_high = by_sev.get("HIGH", 0)
    n_med = by_sev.get("MEDIUM", 0)
    n_low = by_sev.get("LOW", 0)
    print(f"  companies compared: {compared}")
    print(f"  total discrepancy rows: {total}")
    print(f"  HIGH genuine: {n_high}  HIGH excluded: {excluded_by_severity.get('HIGH', 0) if excluded_by_severity else 0}")
    print(f"  MEDIUM genuine: {n_med}  MEDIUM excluded: {excluded_by_severity.get('MEDIUM', 0) if excluded_by_severity else 0}")
    print(f"  LOW genuine: {n_low}  LOW excluded: {excluded_by_severity.get('LOW', 0) if excluded_by_severity else 0}")
    print(f"  flagged rows by metric: {dict(by_metric)}")
    print(f"  by severity: {dict(by_sev)}")


# ---------------------------------------------------------------------------
# shared CSV helpers
# ---------------------------------------------------------------------------
def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing input file: {path}")
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_metrics(out: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker",
        "ok",
        "error",
        "fiscal_year",
        "fiscal_year_end",
        "price",
        "market_cap",
        "revenue",
        "net_income",
        "total_assets",
        "total_liabilities",
        "operating_cash_flow",
        "capital_expenditure",
        "free_cash_flow",
        "shares_fy",
        "shares_current",
        "stockholders_equity",
        "eps",
        "pe_ratio",
        "fcf_yield",
        "roe",
        "net_margin",
    ]
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="validate_sp500.py")
    p.add_argument(
        "step",
        choices=["constituents", "sample", "vi", "external", "compare", "all"],
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=None, help="restrict to N tickers")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    DATA_DIR.mkdir(exist_ok=True)

    const = DATA_DIR / "sp500_constituents.csv"
    sample = DATA_DIR / "validation_sample_200.csv"
    vi_out = DATA_DIR / "validation_value_investing_200.csv"
    ext_out = DATA_DIR / "validation_external_200.csv"
    disc = DATA_DIR / "validation_discrepancies_200.csv"

    if args.step in ("constituents", "all"):
        if not const.exists() or args.step == "constituents":
            print(f"[{_now()}] constituents")
            build_constituents(const, args.verbose)
    if args.step in ("sample", "all"):
        print(f"[{_now()}] sample")
        build_sample(sample, args.seed, args.limit)
    if args.step in ("vi", "all"):
        print(f"[{_now()}] vi")
        build_vi_metrics(vi_out, args.limit)
    if args.step in ("external", "all"):
        print(f"[{_now()}] external")
        build_external_metrics(ext_out, args.limit)
    if args.step in ("compare", "all"):
        print(f"[{_now()}] compare")
        build_discrepancies(disc)


if __name__ == "__main__":
    main()