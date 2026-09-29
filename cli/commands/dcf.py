"""`dcf` — discounted cash flow valuation (labeled not-from-canon).

This command is a supplementary valuation tool. It is explicitly NOT a
methodology: the output carries ``source="not-from-canon"`` and never
appears in ``compare-methodologies`` or ``methodologies list``.
"""

from __future__ import annotations

from dataclasses import replace

from backend.valuation.base import SOURCE
from cli.formatters import (
    dim,
    fmt_dollar,
    fmt_pct,
    green,
    print_header,
    print_key_value,
    print_section,
    print_table,
    red,
    yellow,
)

_VERDICT_COLORS = {
    "UNDERVALUED": green,
    "FAIR": yellow,
    "OVERVALUED": red,
    "INSUFFICIENT_DATA": dim,
}

_VARIANT_NAMES = {
    "standard": "standard DCF (free cash flow)",
    "reit": "REIT — funds from operations",
    "ddm_financial": "financial — dividend discount model",
    "hyper_growth": "hyper-growth — observed positive FCF",
}

_BASE_LABELS = {
    "standard": "FCF base",
    "reit": "FFO base",
    "ddm_financial": "Dividend per share",
    "hyper_growth": "Normalized FCF base",
}


def register(subparsers):
    p = subparsers.add_parser(
        "dcf",
        help="Two-stage DCF valuation (not-from-canon, not a methodology)",
        description=(
            "Two-stage discounted cash flow valuation. Labeled not-from-canon: "
            "it is a practical addition to the book-derived methodologies, "
            "never part of them."
        ),
    )
    p.add_argument("ticker", help="Ticker to value (e.g. AAPL)")
    p.add_argument(
        "--wacc",
        type=float,
        default=None,
        help="Override the WACC (e.g. 0.10)",
    )
    p.add_argument(
        "--growth",
        type=float,
        default=None,
        help="Override growth years 1-5 (e.g. 0.08)",
    )
    p.add_argument(
        "--terminal-growth",
        type=float,
        default=None,
        help="Override terminal growth (e.g. 0.03)",
    )
    p.set_defaults(func=_run)


def _run(args):
    from backend.app.cli import build_financial_repository
    from backend.services.price_service import get_price_service
    from backend.valuation.base import DCFAssumptions
    from backend.valuation.dcf import DCFValuation

    assumptions = DCFAssumptions()
    if args.wacc is not None:
        assumptions = replace(assumptions, wacc_override=float(args.wacc))
    if args.growth is not None:
        assumptions = replace(assumptions, growth_override=float(args.growth))
    if args.terminal_growth is not None:
        assumptions = replace(assumptions, terminal_growth=float(args.terminal_growth))

    repo = build_financial_repository()
    rows = repo.get_best_available(args.ticker)
    result = DCFValuation(assumptions).evaluate(args.ticker, rows, get_price_service())
    _render(result)


def _render(result):
    ticker = result.ticker or ""
    print_header(f"DCF Valuation — {ticker} ({SOURCE})")

    if result.verdict == "INSUFFICIENT_DATA":
        print_key_value("Verdict", _verdict_color("INSUFFICIENT_DATA"))
        print_section("Notes")
        for reason in result.reasons:
            print(f"  {dim('•')} {reason}")
        if result.missing_inputs:
            print(f"  {dim('•')} Missing: {', '.join(result.missing_inputs)}")
        _print_source_footer()
        return

    color = _VERDICT_COLORS.get(result.verdict, lambda t: t)
    print_key_value(
        "Intrinsic value per share", fmt_dollar(result.intrinsic_value_per_share)
    )
    print_key_value("Current price", fmt_dollar(result.current_price))
    print_key_value("Margin of safety", fmt_pct(result.margin_of_safety))
    print_key_value("Verdict", color(result.verdict))
    print_key_value("Variant", _VARIANT_NAMES.get(result.variant, result.variant))

    print_section("Assumptions")
    discount_label = "Cost of equity" if result.variant == "ddm_financial" else "WACC"
    disc_value = result.wacc
    wacc_label = f"{disc_value:.2%}" if disc_value is not None else "N/A"
    print_key_value(discount_label, wacc_label)
    base_label = _BASE_LABELS.get(result.variant, "FCF base")
    if result.fcf_years is None:
        base_text = base_label
    elif (result.fcf_years or 0) >= 3:
        base_text = f"{base_label} (3y avg)"
    elif result.fcf_years == 2:
        base_text = f"{base_label} (2y avg)"
    else:
        base_text = f"{base_label} (1y)"
    print_key_value(base_text, fmt_dollar(result.fcf_base))
    print_key_value("Growth years 1-5", fmt_pct(result.growth_1_5))
    print_key_value("Growth years 6-10", fmt_pct(result.growth_6_10))
    print_key_value("Terminal growth", fmt_pct(result.terminal_growth))
    print_key_value("Shares outstanding", _fmt_shares(result.shares_outstanding))

    _render_sensitivity(result)

    print_section("Notes")
    for reason in result.reasons:
        print(f"  {dim('•')} {reason}")
    print(f"  {dim('•')} This valuation is NOT part of any book-derived methodology.")
    print(
        f"  {dim('•')} It is labeled not-from-canon and is not shown in compare-methodologies."
    )
    print(
        f"  {dim('•')} Sensitive to WACC and growth assumptions; see valuation/README."
    )
    _print_source_footer()


def _render_sensitivity(result):
    if not result.sensitivity or result.wacc is None or result.growth_1_5 is None:
        return
    print_section("Sensitivity (intrinsic value per share)")
    headers = [
        ("WACC \\ Growth", 0),
        ("g-2%", 1),
        ("g", 1),
        ("g+2%", 1),
    ]
    rows = []
    for dw in (-0.02, 0.0, 0.02):
        w = result.wacc + dw
        cells = []
        for dg in (-0.02, 0.0, 0.02):
            value = result.sensitivity.get((w, result.growth_1_5 + dg))
            cells.append(fmt_dollar(value) if value is not None else dim("—"))
        w_label = "wacc-2%" if dw < 0 else ("wacc" if dw == 0 else "wacc+2%")
        rows.append([w_label] + cells)
    print_table(headers, rows)


def _verdict_color(verdict: str):
    return _VERDICT_COLORS.get(verdict, lambda t: t)(verdict)


def _fmt_shares(shares):
    if shares is None:
        return dim("N/A")
    return f"{shares:,.0f}"


def _print_source_footer():
    print()
    print(
        f"  {dim('Source: not-from-canon — DCF approximation, not a rule from any book.')}"
    )
