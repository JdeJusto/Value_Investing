"""`financials` — balance-sheet view for one ticker.

Thin presentation layer over :class:`FinancialsViewService`. The current
layout is a flat, two-section balance sheet (assets / liabilities + equity)
rather than the Streamlit T-view; see the TODO below.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace

from backend.services.demo_mode import is_demo
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
_ANCHOR_CONCEPTS = (
    set(TOTAL_CONCEPTS["total_assets"])
    | set(TOTAL_CONCEPTS["total_liabilities"])
    | set(_EQUITY_TOTAL_CONCEPTS)
    | {concept for concepts in MASS_SUBTOTAL_CONCEPTS.values() for concept in concepts}
    | {"Equity", "ShareholdersEquity", "TotalEquityGrossMinorityInterest"}
)
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
    years = max(1, min(int(args.years), 20))
    service = FinancialsViewService()
    try:
        facts = None if is_demo() else service.fetch_facts(ticker, args.period, years)
        view = service.build(ticker, args.period, max_years=years, facts=facts)
    except Exception as exc:
        print(f"  {red('ERROR:')} Could not load financials for {ticker}: {exc}")
        raise SystemExit(3) from exc

    if view is None:
        print(f"  {red('ERROR:')} No financial facts stored for {ticker}")
        raise SystemExit(2)

    year = _select_year(view)
    if facts:
        view = _filter_to_latest_period(view, facts, year)
    totals = _totals(view, year)

    if args.json:
        print(
            json.dumps(_build_json_payload(view, year, totals), indent=2, default=str)
        )
        return

    _render(view, year, totals)


def _filter_to_latest_period(view, facts, year: int):
    """Keep balance rows filed at the selected year's own period_end.

    FDB stores prior-year comparatives under the filing's fiscal-year bucket;
    without this filter a concept only tagged in a comparative (MRX equity)
    would leak into the selected year.
    """
    anchors: dict[str, str] = {}
    for fact in facts:
        if int(fact.get("fiscal_year") or 0) != year:
            continue
        concept = str(fact.get("concept") or "")
        period = str(fact.get("period_end") or "")
        if concept in _ANCHOR_CONCEPTS and period:
            anchors[period] = max(anchors.get(period, ""), period)
    if not anchors:
        return view
    anchor = max(anchors)
    allowed = {
        str(fact.get("concept") or "")
        for fact in facts
        if int(fact.get("fiscal_year") or 0) == year
        and str(fact.get("period_end") or "") == anchor
    }
    return replace(
        view,
        balance_sheet=[row for row in view.balance_sheet if row.concept in allowed],
        other=[row for row in view.other if row.concept in allowed],
    )


def _items(rows) -> list[dict]:
    return [
        {"concept": concept, "label": label, "value": value}
        for label, value, concept in rows
    ]


def _build_json_payload(view, year: int, totals: dict) -> dict:
    """Structured JSON contract for ``vi financials --json``.

    Groups the balance lines into assets and liabilities/equity, keeps the
    flat ``balance_sheet`` list for compatibility, and exposes the derived
    flags and balance check.
    """
    assets, liabilities = _rows_by_side(view, year)
    groups = {
        "assets_current": [],
        "assets_noncurrent": [],
        "liab_current": [],
        "liab_noncurrent": [],
        "equity": [],
    }
    for item in assets + liabilities:
        mass = concept_mass(item[2])
        if mass in groups:
            groups[mass].append(item)

    assets_current = _find_row(view, MASS_SUBTOTAL_CONCEPTS["assets_current"], year)
    assets_noncurrent = _find_row(
        view, MASS_SUBTOTAL_CONCEPTS["assets_noncurrent"], year
    )
    liab_current = _find_row(view, MASS_SUBTOTAL_CONCEPTS["liab_current"], year)
    liab_noncurrent = _find_row(view, MASS_SUBTOTAL_CONCEPTS["liab_noncurrent"], year)

    return {
        "ticker": view.ticker,
        "company_name": view.company_name,
        "fiscal_period": view.fiscal_period,
        "fiscal_year": year,
        "assets": {
            "current": _items(groups["assets_current"]),
            "non_current": _items(groups["assets_noncurrent"]),
            "total_current": _parse_money(_value(assets_current, year)),
            "total_non_current": _parse_money(_value(assets_noncurrent, year)),
            "total": totals["assets"],
        },
        "liabilities_equity": {
            "current": _items(groups["liab_current"]),
            "non_current": _items(groups["liab_noncurrent"]),
            "equity": _items(groups["equity"]),
            "total_current": _parse_money(_value(liab_current, year)),
            "total_non_current": _parse_money(_value(liab_noncurrent, year)),
            "total_equity": totals["equity"],
            "total": totals["liabilities_equity"],
        },
        "derived": {
            "liabilities": totals["has_derived_liabilities"],
            "equity": totals["partial_equity"],
        },
        "balanced": totals["balanced"],
        "delta": totals["delta"],
        # Compatibility: the flat view consumers already knew.
        "balance_sheet": [asdict(row) for row in view.balance_sheet],
    }


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
    for row in list(view.balance_sheet) + list(view.other):
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


SECTION_HEADERS = {
    "assets_current": "CURRENT ASSETS",
    "assets_noncurrent": "NON-CURRENT ASSETS",
    "liab_current": "CURRENT LIABILITIES",
    "liab_noncurrent": "NON-CURRENT LIABILITIES",
    "equity": "SHAREHOLDERS' EQUITY",
}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _pad_visible(text: str, width: int) -> str:
    """Pad by visible width, ignoring ANSI color codes."""
    visible = _ANSI.sub("", text)
    return text + " " * max(0, width - len(visible))


def _line(label: str, value: str, *, indent: int = 4) -> str:
    return f"{' ' * indent}{label[:24]:<24}{value:>10}"


def _subtotal_line(label: str, value: float | None) -> str:
    """Bold subtotal with the full section name (no label truncation)."""
    return theme.bold(f"  {label:<29}{_money(value):>9}")


def _mass_items(view, year: int, mass: str) -> list[tuple[str, str]]:
    """Detail lines of one mass, excluding the subtotal concepts themselves."""
    assets, liabilities = _rows_by_side(view, year)
    rows = assets if MASS_COLUMN[mass] == "assets" else liabilities
    subtotal_concepts = set(MASS_SUBTOTAL_CONCEPTS.get(mass, ()))
    return [
        (label, value)
        for label, value, concept in rows
        if concept_mass(concept) == mass and concept not in subtotal_concepts
    ]


def _mass_subtotal(
    view, year: int, mass: str, items: list[tuple[str, str]]
) -> float | None:
    row = _find_row(view, MASS_SUBTOTAL_CONCEPTS.get(mass, []), year)
    subtotal = _parse_money(_value(row, year))
    if subtotal is not None:
        return subtotal
    values = [
        parsed
        for parsed in (_parse_money(value) for _label, value in items)
        if parsed is not None
    ]
    return sum(values) if values else None


def _section_lines(view, year: int, mass: str) -> list[str]:
    items = _mass_items(view, year, mass)
    header = SECTION_HEADERS[mass]
    lines = [theme.section_header(header), theme.section_rule(header)]
    for label, value in items:
        lines.append(_line(label, _short(value)))
    lines.append(
        _subtotal_line(
            f"Total {header.lower()}",
            _mass_subtotal(view, year, mass, items),
        )
    )
    lines.append("")
    return lines


def _total_line(label: str, value: float | None, *, marked: bool = False) -> str:
    text = f"{label:<30}{_money(value):>10}"
    if marked:
        text += " *"
    return theme.bold(text)


def _render(view, year: int, totals: dict) -> None:
    theme.print_header(
        f"Financials · {view.ticker}",
        f"FY{year} · {view.fiscal_period} · source: Financial-DataBase (SEC EDGAR)",
    )

    derived = totals["has_derived_liabilities"]
    partial = totals["partial_equity"]

    left: list[str] = []
    for mass in ("assets_current", "assets_noncurrent"):
        left.extend(_section_lines(view, year, mass))

    right: list[str] = []
    for mass in ("liab_current", "liab_noncurrent", "equity"):
        right.extend(_section_lines(view, year, mass))

    for index in range(max(len(left), len(right))):
        left_line = _pad_visible(left[index], 40) if index < len(left) else " " * 40
        right_line = right[index] if index < len(right) else ""
        print(f"  {left_line}  {right_line}".rstrip())

    print("  " + "─" * 40 + "  " + "─" * 40)
    left_total = _total_line("TOTAL ASSETS", totals["assets"])
    right_totals = [
        _total_line("TOTAL LIABILITIES", totals["liabilities"], marked=derived),
        _total_line(
            "TOTAL EQUITY" + (" *" if partial else ""),
            totals["equity"],
        ),
        _total_line(
            "TOTAL LIABILITIES + EQUITY",
            totals["liabilities_equity"],
        ),
    ]
    for index in range(max(1, len(right_totals))):
        left_line = _pad_visible(left_total, 40) if index == 0 else " " * 40
        right_line = right_totals[index] if index < len(right_totals) else ""
        print(f"  {left_line}  {right_line}".rstrip())

    if totals["balanced"] is True and partial:
        print(f"  {theme.gold('⚠ Balanced (partial equity — see caption)')}")
    elif totals["balanced"] is True:
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
