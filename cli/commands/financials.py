"""`financials` — balance-sheet view for one ticker.

Thin presentation layer over :class:`FinancialsViewService`. The current
layout is a flat, two-section balance sheet (assets / liabilities + equity)
rather than the Streamlit T-view; see the TODO below.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict

from backend.services.financials_view_service import FinancialsViewService
from cli import theme
from cli.formatters import red
from ui.balance_map import (
    MASS_COLUMN,
    MASS_ORDER,
    MASS_SUBTOTAL_CONCEPTS,
    MEMORANDUM_CONCEPTS,
    TOTAL_CONCEPTS,
    concept_mass,
)

_MONEY = re.compile(r"\(?\$?\s*(-?[\d,.]+)\s*([KMBT])?\s*\)?")
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_EQUITY_TOTAL_CONCEPTS = MASS_SUBTOTAL_CONCEPTS["equity"]
_RETAINED_EARNINGS = {"RetainedEarnings", "RetainedEarningsAccumulatedDeficit"}
_TOTAL_ONLY = (
    set(TOTAL_CONCEPTS["total_assets"])
    | set(TOTAL_CONCEPTS["total_liabilities"])
    | set(_EQUITY_TOTAL_CONCEPTS)
    | {"LiabilitiesAndStockholdersEquity"}
)
_SUBTOTAL_SIDES = {
    **{concept: "assets" for concept in MASS_SUBTOTAL_CONCEPTS["assets_current"]},
    **{concept: "assets" for concept in MASS_SUBTOTAL_CONCEPTS["assets_noncurrent"]},
    **{concept: "liabilities" for concept in MASS_SUBTOTAL_CONCEPTS["liab_current"]},
    **{concept: "liabilities" for concept in MASS_SUBTOTAL_CONCEPTS["liab_noncurrent"]},
    **{concept: "liabilities" for concept in _EQUITY_TOTAL_CONCEPTS},
}
_LIABILITY_TERMS = (
    "liabilit",
    "payable",
    "equity",
    "capital",
    "stock",
    "preferred",
    "treasury",
    "retained",
    "earnings",
    "deficit",
    "comprehensive",
    "minority",
)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "financials",
        help="Show the balance sheet for a ticker",
        description=(
            "Render the latest balance sheet from Financial-DataBase. The "
            "layout is a flat two-section table; a two-column T-view is "
            "tracked as a future enhancement."
        ),
    )
    parser.add_argument("ticker", help="Ticker (e.g. AAPL)")
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Number of fiscal years to load (default: 5)",
    )
    parser.add_argument(
        "--period",
        default="FY",
        help="Fiscal period (default: FY)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw FinancialsView payload as JSON",
    )
    parser.set_defaults(func=_run)


def _run(args) -> None:
    ticker = args.ticker.upper().strip()
    try:
        view = FinancialsViewService().build(
            ticker,
            args.period,
            max_years=max(1, min(int(args.years), 20)),
        )
    except Exception as exc:
        print(f"  {red('ERROR:')} Could not load financials for {ticker}: {exc}")
        raise SystemExit(3) from exc

    if view is None:
        print(f"  {red('ERROR:')} No financial facts stored for {ticker}")
        raise SystemExit(2)

    year = _select_year(view)
    totals = _totals(view, year)
    payload = asdict(view)
    payload.update(
        {
            "fiscal_year": year,
            "totals": totals,
            "balanced": totals["balanced"],
            "delta": totals["delta"],
            "derived_liabilities": year in set(view.derived_liability_years),
            "partial_equity": totals["partial_equity"],
        }
    )

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return

    _render(view, year, totals)


def _select_year(view) -> int:
    """Newest fiscal year with at least one balance-sheet value.

    FDB can carry a phantom current year with only fee/offering facts; the
    CLI must not open on it (same rule as the Streamlit T-view).
    """
    for year in view.years:
        if any(row.values.get(year) for row in view.balance_sheet):
            return year
    return view.years[0]


def _parse_money(text: str | None) -> float | None:
    if not text:
        return None
    raw = str(text).strip()
    if raw in {"", "—", "-"}:
        return None
    match = _MONEY.search(raw)
    if not match:
        return None
    negative = raw.startswith("(")
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    value *= _SUFFIX.get(match.group(2) or "", 1.0)
    return -value if negative else value


def _find_row(view, concepts, year: int):
    for concept in concepts:
        for row in view.balance_sheet:
            if row.concept == concept and row.values.get(year):
                return row
    return None


def _value(row, year: int) -> str | None:
    return row.values.get(year) if row is not None else None


def _totals(view, year: int) -> dict:
    assets_row = _find_row(view, TOTAL_CONCEPTS["total_assets"], year)
    liabilities_row = _find_row(view, TOTAL_CONCEPTS["total_liabilities"], year)
    equity_row = _find_row(view, _EQUITY_TOTAL_CONCEPTS, year)
    retained_row = _find_row(view, _RETAINED_EARNINGS, year)
    combined_row = _find_row(view, {"LiabilitiesAndStockholdersEquity"}, year)

    assets = _parse_money(_value(assets_row, year))
    liabilities = _parse_money(_value(liabilities_row, year))
    equity = _parse_money(_value(equity_row, year))
    partial_equity = equity_row is None and retained_row is not None
    if partial_equity:
        equity = _parse_money(_value(retained_row, year))

    liabilities_equity = _parse_money(_value(combined_row, year))
    if liabilities_equity is None and liabilities is not None and equity is not None:
        liabilities_equity = liabilities + equity

    delta = None
    balanced = None
    if assets is not None and liabilities is not None and equity is not None:
        delta = assets - liabilities - equity
        balanced = abs(delta) <= max(1.0, abs(assets) * 0.01)
    elif assets is not None and combined_row is not None:
        combined = _parse_money(_value(combined_row, year))
        balanced = combined == assets if combined is not None else None
        delta = (assets - combined) if combined is not None else None

    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "liabilities_equity": liabilities_equity,
        "delta": delta,
        "balanced": balanced,
        "partial_equity": partial_equity,
        "has_derived_liabilities": year in set(view.derived_liability_years),
    }


def _side(concept: str) -> str:
    mass = concept_mass(concept)
    if mass:
        return MASS_COLUMN[mass]
    if concept in _SUBTOTAL_SIDES:
        return _SUBTOTAL_SIDES[concept]
    lowered = concept.lower()
    if any(term in lowered for term in _LIABILITY_TERMS):
        return "liabilities"
    return "assets"


def _rows_by_side(view, year: int):
    assets, liabilities = [], []
    for row in view.balance_sheet:
        if not row.values.get(year):
            continue
        if row.concept in _TOTAL_ONLY or row.concept in MEMORANDUM_CONCEPTS:
            continue
        if row.unit in {"shares", "pure"} or row.unit.endswith("/shares"):
            continue
        if concept_mass(row.concept) is None and row.concept not in _SUBTOTAL_SIDES:
            continue
        target = assets if _side(row.concept) == "assets" else liabilities
        target.append((row.label, row.values[year], row.concept))
    order = {mass: index for index, mass in enumerate(MASS_ORDER)}
    key = lambda item: (order.get(concept_mass(item[2]), len(order)), item[0])
    assets.sort(key=key)
    liabilities.sort(key=key)
    return assets, liabilities


def _render(view, year: int, totals: dict) -> None:
    theme.print_header(
        f"Financials · {view.ticker}",
        f"FY{year} · {view.fiscal_period} · source: Financial-DataBase (SEC EDGAR)",
    )

    assets, liabilities = _rows_by_side(view, year)
    derived = totals["has_derived_liabilities"]
    partial = totals["partial_equity"]

    print(f"  {'ASSETS':<38}LIABILITIES + EQUITY")
    print("  " + "─" * 38 + "  " + "─" * 38)
    for index in range(max(len(assets), len(liabilities))):
        left = assets[index] if index < len(assets) else ("", "", "")
        right = liabilities[index] if index < len(liabilities) else ("", "", "")
        left_value = _short(
            _mark(left[1], derived and left[2] in {"Liabilities", "LiabilitiesTotal"})
        )
        right_value = _short(
            _mark(right[1], derived and right[2] in {"Liabilities", "LiabilitiesTotal"})
        )
        print(
            f"  {left[0][:28]:<28}{left_value:>10}  "
            f"{right[0][:28]:<28}{right_value:>10}"
        )
    print("  " + "─" * 38 + "  " + "─" * 38)
    print(f"  {'TOTAL ASSETS':<28}{_big(totals['assets'])}")
    print(
        f"  {'':<28}{'':>10}  {'TOTAL LIABILITIES':<28}"
        f"{_big(totals['liabilities'], derived)}"
    )
    print(
        f"  {'':<28}{'':>10}  {'TOTAL EQUITY' + (' *' if partial else ''):<28}"
        f"{_big(totals['equity'])}"
    )
    print(
        f"  {'':<28}{'':>10}  {'TOTAL LIABILITIES + EQUITY':<28}"
        f"{_big(totals['liabilities_equity'])}"
    )

    if totals["balanced"] is True:
        print(f"  {theme.neon_cyan('✓ Balanced')} (Δ = {_money(totals['delta'])})")
    elif totals["balanced"] is False:
        print(f"  {theme.gold('⚠ Does not balance')} (Δ = {_money(totals['delta'])})")
    else:
        print(f"  {theme.dim('Partial balance — totals missing to verify.')}")
    if derived:
        print(theme.dim("  * Derived (Assets − Equity); not reported in filing."))
    if partial:
        print(
            theme.dim(
                "  * Partial equity (RetainedEarnings only; full equity not reported)."
            )
        )
    for warning in view.extraction_warnings:
        lowered = warning.lower()
        if "facts in this window" in lowered or "derived from assets" in lowered:
            continue
        print(theme.dim(f"  {warning}"))


def _mark(value: str, marked: bool) -> str:
    return f"{value} *" if marked else value


def _short(value: str) -> str:
    parsed = _parse_money(value)
    return _money(parsed) if parsed is not None else value


def _big(value: float | None, marked: bool = False) -> str:
    text = _mark(_money(value), marked).rjust(10)
    return theme.big_number(text)


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1e9:
        return f"{sign}${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"{sign}${value / 1e6:.2f}M"
    if value >= 1e3:
        return f"{sign}${value / 1e3:.2f}K"
    return f"{sign}${value:.2f}"


# TODO(v0.21): render the side-by-side T-view layout (two columns with
# subtotals and totals). The flat two-section table keeps the command useful
# without duplicating the Streamlit balance model in the CLI.
