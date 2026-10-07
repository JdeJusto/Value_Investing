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

from rich.text import Text

from backend.adapters.database.repositories.company_repository import CompanyRepository
from backend.app.cli import (
    add_demo_argument,
    add_refresh_arguments,
    build_screener_service,
    refresh_analysis_inputs,
)
from backend.services import cli_output
from backend.services.historical_valuation_service import HistoricalValuationService
from cli.commands.preflight import require_known_tickers
from cli.formatters import (
    fmt_dollar,
    fmt_pct,
    fmt_ratio,
    valuation_table,
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
    """Format a metric; a missing value renders as muted ``N/A``."""
    if value is None:
        return Text("N/A", style=cli_output.MUTED)
    return formatter(value)


def _na():
    """Missing text as muted rich Text (styling survives inside panels)."""
    return Text("N/A", style=cli_output.MUTED)


def _heading(title: str) -> None:
    """Numbered section heading: bold title over a dim rule (column 0)."""
    console = cli_output.get_console()
    console.print(cli_output.heading(title, indent=0), soft_wrap=True)
    console.print(cli_output.rule(indent=0), soft_wrap=True)


def _company_overview(ticker: str, name) -> tuple:
    try:
        company = CompanyRepository().find_by_ticker(ticker)
        return (company.sector if company else None), (
            company.industry if company else None
        )
    except Exception:  # noqa: BLE001
        return None, None


def _print_section(ticker, name=None, price=None, market_cap=None, sector=None):
    """Command banner: ticker in the title, headline facts in the body."""
    facts = "  ·  ".join(
        part
        for part in (
            name,
            f"Price {cli_output.format_currency(price)}",
            f"Market Cap {cli_output.format_currency(market_cap)}",
            f"Sector {sector or 'N/A'}",
        )
        if part
    )
    cli_output.print_banner(f"Comprehensive analysis: {ticker}", Text(facts))


def _section_overview(row_input, sector, industry):
    _heading("1) Company overview")
    cli_output.print_kv(
        [
            ("Ticker", row_input["ticker"]),
            ("Name", row_input["name"] or _na()),
            ("Sector", sector or _na()),
            ("Industry", industry or _na()),
        ],
        key_width=14,
    )


def _section_price(price, market_cap, per, pb, fcf_yield, ev_ebit, shares, no_prices):
    _heading("2) Real-time price and valuation")
    if no_prices:
        cli_output.get_console().print(
            Text(
                "     (--no-prices) Price not fetched in real time.",
                style=cli_output.WARNING,
            ),
            soft_wrap=True,
        )
    cli_output.print_kv(
        [
            ("Price", _fmt(price, fmt_dollar)),
            ("Shares outstanding", f"{shares:,}" if shares else _na()),
            ("Market Cap", _fmt(market_cap, fmt_dollar)),
            ("PER", _fmt(per, lambda v: fmt_ratio(v, 1))),
            ("P/B", _fmt(pb, lambda v: fmt_ratio(v, 2))),
            ("FCF Yield", _fmt(fcf_yield, fmt_pct)),
            ("EV/EBIT", _fmt(ev_ebit, lambda v: fmt_ratio(v, 1))),
        ],
        key_width=18,
    )


def _section_fundamentals(row_input):
    _heading("3) Fundamental metrics")
    cli_output.print_kv(
        [
            ("ROE", _fmt(row_input.get("roe"), fmt_pct)),
            ("ROIC", _fmt(row_input.get("roic"), fmt_pct)),
            ("Operating margin", _fmt(row_input.get("operating_margin"), fmt_pct)),
            ("Net margin", _fmt(row_input.get("net_margin"), fmt_pct)),
            ("Revenue growth", _fmt(row_input.get("revenue_growth"), fmt_pct)),
            ("Debt / Equity", _fmt(row_input.get("debt_to_equity"), fmt_ratio)),
            ("Free Cash Flow", _fmt(row_input.get("fcf"), fmt_dollar)),
            ("Owner Earnings", _fmt(row_input.get("owner_earnings"), fmt_dollar)),
            ("CROIC", _fmt(row_input.get("croic"), fmt_pct)),
        ],
        key_width=24,
    )


def _section_quality(row_input, quality):
    _heading("4) Company quality")
    composite = row_input.get("composite_score") or {}
    moat = row_input.get("moat_analysis") or {}
    confidence = composite.get("confidence")
    cli_output.print_kv(
        [
            (
                "Buffett score",
                _fmt(row_input.get("buffett_score"), lambda v: f"{v:.1f}"),
            ),
            ("Moat", moat.get("moat_type") or _na()),
            ("Rating", composite.get("rating") or _na()),
            (
                "Confidence",
                cli_output.confidence_text(confidence) if confidence else _na(),
            ),
            ("Total score", _fmt(composite.get("total_score"), lambda v: f"{v:.1f}")),
            ("DCF value", _fmt(row_input.get("dcf_value"), fmt_dollar)),
            ("Margin of safety", _fmt(row_input.get("dcf_margin_of_safety"), fmt_pct)),
        ],
        key_width=20,
    )
    if quality:
        cli_output.print_kv(
            [
                ("Average ROIC", _fmt(quality.get("roic_mean"), fmt_pct)),
                ("Revenue CAGR", _fmt(quality.get("revenue_cagr"), fmt_pct)),
            ],
            key_width=20,
        )
    insight = row_input.get("insight")
    if insight:
        text = insight if isinstance(insight, str) else "; ".join(insight)
        cli_output.get_console().print(
            cli_output.kv_line(
                "Insight", text, key_width=20, indent="     ", align="left", sep=" "
            ),
            soft_wrap=True,
        )


def render_dcf_section(result) -> None:
    """Render the supplementary DCF block (not-from-canon) for analyze-full."""
    from rich.console import Group

    from backend.valuation.base import SOURCE
    from backend.valuation.dcf import INSUFFICIENT_DATA

    console = cli_output.get_console()
    lines: list = []
    if result.verdict == INSUFFICIENT_DATA:
        lines.append(
            cli_output.kv_line("Verdict", Text(result.verdict, style=cli_output.MUTED))
        )
        reason = "; ".join(result.reasons) if result.reasons else "-"
        lines.append(cli_output.kv_line("Reason", reason))
        if result.missing_inputs:
            lines.append(
                cli_output.kv_line("Missing", ", ".join(result.missing_inputs))
            )
    else:
        verdict_style = {
            "UNDERVALUED": cli_output.ACCENT,
            "FAIR": cli_output.WARNING,
            "OVERVALUED": cli_output.DANGER,
        }.get(result.verdict, "")
        lines.append(
            cli_output.kv_line(
                "Intrinsic value/share",
                _fmt(result.intrinsic_value_per_share, fmt_dollar),
            )
        )
        lines.append(
            cli_output.kv_line("Current price", _fmt(result.current_price, fmt_dollar))
        )
        lines.append(
            cli_output.kv_line(
                "Margin of safety", _fmt(result.margin_of_safety, fmt_pct)
            )
        )
        lines.append(
            cli_output.kv_line("Verdict", Text(result.verdict, style=verdict_style))
        )
        fcf_label = {1: "FCF base (1y)", 2: "FCF base (2y avg)"}.get(
            result.fcf_years, "FCF base (3y avg)"
        )
        lines.append(Text(""))
        lines.append(cli_output.heading("Assumptions", indent=0))
        for label, value in (
            ("WACC", _fmt(result.wacc, lambda v: f"{v:.2%}")),
            (fcf_label, _fmt(result.fcf_base, fmt_dollar)),
            ("Growth years 1-5", _fmt(result.growth_1_5, fmt_pct)),
            ("Growth years 6-10", _fmt(result.growth_6_10, fmt_pct)),
            ("Terminal growth", f"{result.terminal_growth:.2%}"),
        ):
            lines.append(
                cli_output.kv_line(
                    label, value, key_width=20, indent="  ", align="left", sep=" : "
                )
            )
    lines.append(Text(""))
    warning = Text()
    warning.append("⚠️ ", style=cli_output.WARNING)
    warning.append("This valuation is NOT part of any book-derived methodology.")
    lines.append(warning)
    lines.append(Text("     It is a practical addition labeled not-from-canon."))
    lines.append(
        Text("     See backend/valuation/README.md for assumptions and limits.")
    )
    console.print()
    cli_output.print_panel(
        cli_output.section_panel(
            f"DCF Valuation (supplementary, {SOURCE})", Group(*lines)
        ),
        console=console,
    )


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
        line = Text("     DCF unavailable:", style=cli_output.DANGER)
        line.append(f" {e}")
        cli_output.get_console().print(line, soft_wrap=True)


def _section_historical(ticker):
    _heading("5) Historical valuation")
    service = HistoricalValuationService()
    console = cli_output.get_console()
    try:
        summary = getattr(service, "get_historical_valuation_summary", None)
        if callable(summary):
            ratios = summary(ticker)
            if ratios:
                console.print(valuation_table(ratios))
                return
        # No structured rows (or none available): keep the text rendering.
        print(service.format_valuation_table(ticker))
    except Exception as e:  # noqa: BLE001
        line = Text("     ERROR:", style=cli_output.DANGER)
        line.append(f" {e}")
        console.print(line, soft_wrap=True)


def _section_risks(row_input):
    _heading("6) Risks / anomalies / triggers")
    console = cli_output.get_console()
    anomalies = row_input.get("anomalies") or []
    if not anomalies:
        console.print(Text("     No anomalies detected."), soft_wrap=True)
    else:
        for a in anomalies:
            desc = a if isinstance(a, str) else str(a)
            line = Text("     • ", style=cli_output.DANGER)
            line.append("Anomaly:", style=cli_output.DANGER)
            line.append(f" {desc}")
            console.print(line, soft_wrap=True)

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
        line = Text("     • ", style=cli_output.WARNING)
        line.append("Trigger:", style=cli_output.WARNING)
        line.append(f" {', '.join(triggers)}")
        console.print(line, soft_wrap=True)
    else:
        console.print(Text("     No active triggers."), soft_wrap=True)

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
    summary = Text(
        f"     Source: {source or 'N/A'}  |  Data confidence: "
        f"{confidence or 'N/A'}  |  Quality: "
    )
    if quality is None:
        summary.append("N/A", style=cli_output.MUTED)
    else:
        summary.append(fmt_pct(quality))
    console.print(summary, soft_wrap=True)


def _run(args):
    service = build_screener_service()
    tickers = [t.upper().strip() for t in args.tickers]
    require_known_tickers(tickers)
    refresh_analysis_inputs(tickers, args, fetch_prices=not args.no_prices)

    console = cli_output.get_console()
    for ticker in tickers:
        try:
            row = service._analyze_ticker(ticker, no_prices=args.no_prices)
        except Exception as e:  # noqa: BLE001
            line = Text(f"\n{ticker} — ", style=cli_output.DANGER)
            line.append("ERROR:", style=cli_output.DANGER)
            line.append(f" {e}")
            console.print(line, soft_wrap=True)
            continue

        if row is None:
            line = Text(f"\n{ticker} — ", style=cli_output.WARNING)
            line.append("Not enough data for the analysis.")
            console.print(line, soft_wrap=True)
            continue

        d = row.extra or {}

        try:
            sector, industry = _company_overview(ticker, row.name)

            _print_section(
                ticker,
                name=row.name,
                price=row.price,
                market_cap=row.market_cap,
                sector=sector,
            )
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
            line = Text("\n  ERROR:", style=cli_output.DANGER)
            line.append(f" generating report for {ticker}: {e}")
            console.print(line, soft_wrap=True)
