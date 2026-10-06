"""analyze-full: consolidated 6-section company report.

One pass, one set of real-time price calls per ticker (only for the tickers
requested). Sections:

  1. Company overview
  2. Real-time price & valuation (PriceService, never persisted)
  3. Fundamental metrics
  4. Quality assessment (Buffett score, moat, rating, DCF)
     + DCF valuation (supplementary, not-from-canon; after quality, before
       the historical table; optional via --no-dcf or config dcf.in_analyze_full)
  5. Historical valuation (P/E and FCF yield by fiscal year)
  6. Risks / anomalies / triggers

Every section degrades to N/A when its data source is unavailable; a failing
ticker never stops the rest of the batch. The supplementary DCF block is
deliberately NOT part of any book methodology and never affects scoring.
"""

from backend.adapters.database.repositories.company_repository import CompanyRepository
from backend.app.cli import (
    add_demo_argument,
    add_refresh_arguments,
    build_screener_service,
    refresh_analysis_inputs,
)
from backend.services.historical_valuation_service import HistoricalValuationService
from cli.commands.preflight import require_known_tickers
from cli.formatters import (
    bold,
    dim,
    fmt_dollar,
    fmt_pct,
    fmt_ratio,
    green,
    print_header,
    print_key_value,
    red,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "analyze-full",
        help="Consolidated 6-section report per ticker",
        description=(
            "Full analysis: overview, real-time price, metrics, "
            "Buffett quality, historical valuation and risks."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="+",
        help="Ticker(s) to analyze (e.g.: AAPL or AAPL MSFT)",
    )
    p.add_argument(
        "--no-prices",
        action="store_true",
        help="Do not fetch real-time prices (section 2 stays partial)",
    )
    p.add_argument(
        "--no-dcf",
        action="store_true",
        help="Skip the supplementary DCF section (not-from-canon)",
    )
    add_refresh_arguments(p)
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _fmt(value, formatter):
    return formatter(value) if value is not None else dim("N/A")


def _company_overview(ticker: str, name) -> tuple:
    try:
        company = CompanyRepository().find_by_ticker(ticker)
        return (company.sector if company else None), (
            company.industry if company else None
        )
    except Exception:  # noqa: BLE001
        return None, None


def _print_section(ticker):
    print_header(f"Comprehensive analysis: {ticker}")


def _section_overview(row_input, sector, industry):
    print(bold("1) Company overview"))
    ov = [
        ("Ticker", row_input["ticker"]),
        ("Name", row_input["name"] or dim("N/A")),
        ("Sector", sector or dim("N/A")),
        ("Industry", industry or dim("N/A")),
    ]
    for label, value in ov:
        print(f"     {label:<14} {value}")


def _section_price(price, market_cap, per, pb, fcf_yield, ev_ebit, shares, no_prices):
    print(bold("2) Real-time price and valuation"))
    if no_prices:
        print(f"     {yellow('(--no-prices) Price not fetched in real time.')}")
    vals = [
        ("Price", _fmt(price, fmt_dollar)),
        ("Shares outstanding", f"{shares:,}" if shares else dim("N/A")),
        ("Market Cap", _fmt(market_cap, fmt_dollar)),
        ("PER", _fmt(per, lambda v: fmt_ratio(v, 1))),
        ("P/B", _fmt(pb, lambda v: fmt_ratio(v, 2))),
        ("FCF Yield", _fmt(fcf_yield, fmt_pct)),
        ("EV/EBIT", _fmt(ev_ebit, lambda v: fmt_ratio(v, 1))),
    ]
    for label, value in vals:
        print(f"     {label:<18} {value}")


def _section_fundamentals(row_input):
    print(bold("3) Fundamental metrics"))
    vals = [
        ("ROE", _fmt(row_input.get("roe"), fmt_pct)),
        ("ROIC", _fmt(row_input.get("roic"), fmt_pct)),
        ("Operating margin", _fmt(row_input.get("operating_margin"), fmt_pct)),
        ("Net margin", _fmt(row_input.get("net_margin"), fmt_pct)),
        ("Revenue growth", _fmt(row_input.get("revenue_growth"), fmt_pct)),
        ("Debt / Equity", _fmt(row_input.get("debt_to_equity"), fmt_ratio)),
        ("Free Cash Flow", _fmt(row_input.get("fcf"), fmt_dollar)),
        ("Owner Earnings", _fmt(row_input.get("owner_earnings"), fmt_dollar)),
        ("CROIC", _fmt(row_input.get("croic"), fmt_pct)),
    ]
    for label, value in vals:
        print(f"     {label:<24} {value}")


def _section_quality(row_input, quality):
    print(bold("4) Company quality"))
    composite = row_input.get("composite_score") or {}
    moat = row_input.get("moat_analysis") or {}
    vals = [
        ("Buffett score", _fmt(row_input.get("buffett_score"), lambda v: f"{v:.1f}")),
        ("Moat", moat.get("moat_type") or dim("N/A")),
        ("Rating", composite.get("rating") or dim("N/A")),
        ("Confidence", composite.get("confidence") or dim("N/A")),
        ("Total score", _fmt(composite.get("total_score"), lambda v: f"{v:.1f}")),
        ("DCF value", _fmt(row_input.get("dcf_value"), fmt_dollar)),
        ("Margin of safety", _fmt(row_input.get("dcf_margin_of_safety"), fmt_pct)),
    ]
    if quality:
        vals.extend(
            [
                ("Average ROIC", _fmt(quality.get("roic_mean"), fmt_pct)),
                ("Revenue CAGR", _fmt(quality.get("revenue_cagr"), fmt_pct)),
            ]
        )
    for label, value in vals:
        print(f"     {label:<20} {value}")
    insight = row_input.get("insight")
    if insight:
        text = insight if isinstance(insight, str) else "; ".join(insight)
        print(f"     Insight: {text}")


def render_dcf_section(result) -> None:
    """Render the supplementary DCF block (not-from-canon) for analyze-full."""
    from backend.valuation.base import SOURCE
    from backend.valuation.dcf import INSUFFICIENT_DATA

    print_header(f"DCF Valuation (supplementary, {SOURCE})")
    if result.verdict == INSUFFICIENT_DATA:
        print_key_value("Verdict", dim(result.verdict))
        reason = "; ".join(result.reasons) if result.reasons else "-"
        print_key_value("Reason", reason)
        if result.missing_inputs:
            print_key_value("Missing", ", ".join(result.missing_inputs))
    else:
        verdict_color = {
            "UNDERVALUED": green,
            "FAIR": yellow,
            "OVERVALUED": red,
        }.get(result.verdict, lambda t: t)
        print_key_value(
            "Intrinsic value/share", _fmt(result.intrinsic_value_per_share, fmt_dollar)
        )
        print_key_value("Current price", _fmt(result.current_price, fmt_dollar))
        print_key_value("Margin of safety", _fmt(result.margin_of_safety, fmt_pct))
        print_key_value("Verdict", verdict_color(result.verdict))
        fcf_label = {1: "FCF base (1y)", 2: "FCF base (2y avg)"}.get(
            result.fcf_years, "FCF base (3y avg)"
        )
        print()
        print(f"  {bold('Assumptions')}")
        for label, value in (
            ("WACC", _fmt(result.wacc, lambda v: f"{v:.2%}")),
            (fcf_label, _fmt(result.fcf_base, fmt_dollar)),
            ("Growth years 1-5", _fmt(result.growth_1_5, fmt_pct)),
            ("Growth years 6-10", _fmt(result.growth_6_10, fmt_pct)),
            ("Terminal growth", f"{result.terminal_growth:.2%}"),
        ):
            print(f"  {label:<20} : {value}")
    print()
    print(
        f"  {yellow('⚠️')} This valuation is NOT part of any book-derived methodology."
    )
    print("     It is a practical addition labeled not-from-canon.")
    print("     See backend/valuation/README.md for assumptions and limits.")


def _dcf_enabled(args) -> bool:
    """True unless --no-dcf or the config disables the DCF section."""
    if getattr(args, "no_dcf", False):
        return False
    try:
        from backend.services.refresh_service import load_dcf_config

        return load_dcf_config().in_analyze_full
    except Exception:  # noqa: BLE001 — config problems must not break the report
        return True


def _section_dcf(ticker, repo=None, price_service=None) -> None:
    """Supplementary DCF section; never raises (degrades to a message)."""
    try:
        from backend.app.cli import build_financial_repository
        from backend.services.price_service import get_price_service
        from backend.valuation.dcf import DCFValuation

        repo = repo if repo is not None else build_financial_repository()
        if price_service is None:
            price_service = get_price_service()
        rows = repo.get_best_available(ticker)
        result = DCFValuation().evaluate(ticker, rows, price_service)
        render_dcf_section(result)
    except Exception as e:  # noqa: BLE001 — a failing DCF must never stop the report
        print(f"     {red('DCF unavailable:')} {e}")


def _section_historical(ticker):
    print(bold("5) Historical valuation"))
    service = HistoricalValuationService()
    try:
        table = service.format_valuation_table(ticker)
    except Exception as e:  # noqa: BLE001
        print(f"     {red('ERROR:')} {e}")
        return
    print(table)


def _section_risks(row_input):
    print(bold("6) Risks / anomalies / triggers"))
    anomalies = row_input.get("anomalies") or []
    if not anomalies:
        print("     No anomalies detected.")
    else:
        for a in anomalies:
            desc = a if isinstance(a, str) else str(a)
            print(f"     {red('Anomaly:')} {desc}")

    triggers = []
    try:
        from backend.alerts.triggers import trigger_label
        from backend.screener.signals import detect_trigger

        trigger = trigger_label(detect_trigger(row_input))
        if trigger:
            triggers.append(trigger)
    except Exception:  # noqa: BLE001, S110
        pass
    if triggers:
        print(f"     {yellow('Trigger:')} {', '.join(triggers)}")
    else:
        print("     No active triggers.")

    piotroski = row_input.get("piotroski_fscore")
    if piotroski is not None:
        print(f"     Piotroski F-Score: {piotroski}/9")
    altman = row_input.get("altman_zscore")
    if altman is not None:
        print(f"     Altman Z-Score: {altman:.2f}")
    score = row_input.get("score")
    if score is not None:
        print(f"     Composite score: {score:.4f}")

    confidence = (row_input.get("composite_score") or {}).get("confidence")
    source = row_input.get("data_source_used")
    quality = row_input.get("data_quality_score")
    print(
        f"     Source: {source or 'N/A'}  |  Data confidence: "
        f"{confidence or 'N/A'}  |  Quality: {fmt_pct(quality) if quality is not None else dim('N/A')}"
    )


def _run(args):
    service = build_screener_service()
    tickers = [t.upper().strip() for t in args.tickers]
    require_known_tickers(tickers)
    refresh_analysis_inputs(tickers, args, fetch_prices=not args.no_prices)

    for ticker in tickers:
        try:
            row = service._analyze_ticker(ticker, no_prices=args.no_prices)
        except Exception as e:  # noqa: BLE001
            print(f"\n{red(ticker)} — {red('ERROR:')} {e}")
            continue

        if row is None:
            print(f"\n{red(ticker)} — Not enough data for the analysis.")
            continue

        d = row.extra or {}

        try:
            sector, industry = _company_overview(ticker, row.name)

            _print_section(ticker)
            _section_overview({"ticker": ticker, "name": row.name}, sector, industry)
            _section_price(
                row.price,
                row.market_cap,
                row.per,
                row.pb,
                row.fcf_yield,
                row.ev_ebit,
                row.shares_outstanding,
                args.no_prices,
            )
            _section_fundamentals(d)
            _section_quality(d, d.get("quality_metrics") or {})
            if _dcf_enabled(args):
                _section_dcf(ticker)
            _section_historical(ticker)
            _section_risks(d)
            print()
            print("-" * 72)
        except Exception as e:  # noqa: BLE001
            print(f"\n  {red('ERROR:')} generating report for {ticker}: {e}")
