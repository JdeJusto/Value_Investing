"""Analysis — single-ticker deep dive with tabs, plus multi-ticker compare.

Reuses the ui_adapter views (methodologies + DCF) and the existing analytics
service for the raw metrics tab. No analysis logic lives here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from backend.services.demo_mode import DEMO_TICKERS, is_demo, is_demo_ticker
from backend.services.financial_statement_parser import load_financial_statement
from backend.services.ui_adapter import (
    fmt_money_short,
    fmt_or_dash,
    render_narrative_preview,
    render_statement_preview,
    run_dcf,
    run_methodologies,
)
from backend.services.ui_format import abbreviate_number
from ui._shared import (
    dataframe_with_download,
    format_pct,
    metric_row,
    page_header,
)
from ui.services import (
    get_price_service,
    load_filings,
    load_fundamentals,
    load_historical_valuation,
    load_quote,
)

DCF_DISCLAIMER = (
    "**not-from-canon** — the DCF is not part of any book methodology and "
    "does not compete with their verdicts. It is a valuation approximation, "
    "sensitive to WACC and growth assumptions."
)
MAX_MULTI_TICKERS = 8


@st.cache_data(ttl=3600, show_spinner=False)
def _load_narrative_cached(record_key: tuple, section_value: str) -> dict:
    """Cached narrative preview keyed by (record fields, section type).

    The demo fixture or the JSON parse cache is read on the first Load
    click; renders within the TTL reuse it. The view/section radios never
    trigger a load on their own (the Load button is the only fetch trigger).
    """
    from types import SimpleNamespace

    from backend.services.narrative_extractor import SectionType, load_narrative_section

    record = SimpleNamespace(**dict(record_key))
    return render_narrative_preview(
        record, SectionType(section_value), load_narrative_section
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _load_financials_cached(ticker: str, fiscal_period: str, max_years: int):
    """Cached (view, insights, alerts) keyed by (ticker, period, years).

    One fact read feeds the tables, the Summary panel and the sidebar alerts
    — no second source. Renders within the TTL reuse it; the data only
    changes on a SEC sync. Demo mode reads the pinned fixtures instead.
    """
    from backend.services.alert_service import AlertService, load_demo_alerts
    from backend.services.financial_insights_service import (
        FinancialInsightsService,
        load_demo_insights,
    )
    from backend.services.financials_view_service import FinancialsViewService

    service = FinancialsViewService()
    if is_demo():
        return (
            service.build(ticker, fiscal_period, max_years),
            load_demo_insights(ticker),
            load_demo_alerts(ticker),
        )
    facts = service.fetch_facts(ticker, fiscal_period, max_years)
    view = service.build(ticker, fiscal_period, max_years, facts=facts, abbreviate=True)
    if view is None or not facts:
        return view, None, None
    report = FinancialInsightsService(facts, ticker, view.company_name).build(
        abbreviate=True
    )
    alerts = AlertService(facts).build(
        ticker, view.company_name, fiscal_period, abbreviate=True
    )
    return view, report, alerts


def main() -> None:
    page_header(
        "Analysis",
        "Six book methodologies + DCF for one ticker; comma-separated list for a quick compare.",
    )
    ticker = st.text_input("Ticker", value="AAPL", max_chars=10, key="an_ticker")
    if is_demo():
        if ticker.strip() and not is_demo_ticker(ticker):
            st.warning(_demo_unsupported_message(ticker.strip().upper()))
        else:
            st.caption(
                f"Demo mode: available tickers are **{', '.join(DEMO_TICKERS)}**. "
                "Any other ticker will show an error."
            )
    multi = st.text_input(
        "Multi-ticker compare (comma-separated, optional)",
        placeholder="AAPL, MSFT, KO",
        key="an_multi",
    )
    if st.button("Analyze", type="primary"):
        names = [name.strip().upper() for name in multi.split(",") if name.strip()]
        st.session_state["an_mode"] = "multi" if names else "single"
        st.session_state["an_tickers"] = (
            names[:MAX_MULTI_TICKERS] if names else [ticker.upper().strip()]
        )
    mode = st.session_state.get("an_mode")
    names = st.session_state.get("an_tickers") or []
    if not mode or not names or not names[0]:
        st.info("Enter a ticker and press Analyze.")
        return
    if mode == "multi":
        if is_demo():
            supported = [name for name in names if is_demo_ticker(name)]
            dropped = [name for name in names if not is_demo_ticker(name)]
            if dropped:
                st.caption(
                    "Demo mode: ignoring tickers without fixtures: "
                    + ", ".join(dropped)
                )
            if not supported:
                st.warning(
                    "None of the requested tickers are in the demo bundle. "
                    f"Demo mode includes: {', '.join(DEMO_TICKERS)}. "
                    "To analyze other tickers, run the app without `VI_DEMO=1` "
                    "and with access to Financial-DataBase."
                )
                return
            names = supported
        for name in names:
            _render_compact(name)
    else:
        _render_single(names[0])


def _demo_unsupported_message(ticker: str) -> str:
    """Actionable guidance for a ticker outside the demo bundle."""
    return (
        f"Ticker `{ticker}` is not in the demo bundle. "
        f"Demo mode includes: {', '.join(DEMO_TICKERS)}. "
        "To analyze other tickers, run the app without `VI_DEMO=1` "
        "and with access to Financial-DataBase."
    )


def _render_missing_fundamentals(ticker: str) -> None:
    """Mode-aware guidance when a ticker has no fundamentals.

    Three distinct situations so the user always knows what to do:
    demo + unsupported ticker (list the bundle), demo + broken fixture
    (report the bug), production + no data (check Financial-DataBase).
    """
    if is_demo() and not is_demo_ticker(ticker):
        st.warning(_demo_unsupported_message(ticker))
    elif is_demo():
        st.error(
            f"Demo fixture for `{ticker}` exists but returned no data. "
            "This is a bug — please report it."
        )
    else:
        st.warning(
            f"No fundamentals found for `{ticker}`. "
            "Verify the ticker is listed on a supported exchange and "
            "that Financial-DataBase has data for it."
        )


def _render_single(ticker: str) -> None:
    rows = load_fundamentals(ticker)
    if not rows:
        _render_missing_fundamentals(ticker)
        return
    quote = load_quote(ticker)
    _price_header(ticker, rows, quote)
    with st.spinner(f"Evaluating methodologies and DCF for {ticker}..."):
        view = run_methodologies(ticker, rows, quote["price"], quote["market_cap"])
        dcf = run_dcf(ticker, rows, get_price_service())
    tabs = st.tabs(
        [
            "Overview",
            "Methodologies",
            "DCF",
            "Historical",
            "Filings",
            "Financials",
            "Raw",
        ]
    )
    with tabs[0]:
        _overview(rows, quote, view)
    with tabs[1]:
        _methodologies(view)
    with tabs[2]:
        _dcf_panel(dcf)
    with tabs[3]:
        _historical(ticker)
    with tabs[4]:
        _filings(ticker)
    with tabs[5]:
        _financials(ticker)
    with tabs[6]:
        _raw(ticker)


def _filings(ticker: str) -> None:
    """Official SEC filings with EDGAR links (nothing is downloaded)."""
    records = load_filings(ticker)
    if not records:
        st.info(
            "No filings stored for this company yet. Sync it first "
            "(`python -m scripts.daily_workflow --refresh`) or try `--demo`."
        )
        return

    available_forms = sorted({record.form_type for record in records})
    available_years = sorted(
        {
            record.effective_fiscal_year
            for record in records
            if record.effective_fiscal_year
        },
        reverse=True,
    )
    preferred = [form for form in ("10-K", "10-Q") if form in available_forms]
    with st.form("filings_filters"):
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            forms = st.multiselect(
                "Form type", available_forms, default=preferred or available_forms[:2]
            )
        with col2:
            years = st.multiselect(
                "Fiscal year", available_years, default=available_years[:5]
            )
        with col3:
            include_amendments = st.checkbox("Include amendments", value=True)
            since = st.date_input("Since (optional)", value=None)
        st.form_submit_button("Apply filters")

    filtered = [
        record
        for record in records
        if (not forms or record.form_type in forms)
        and (not years or record.effective_fiscal_year in years)
        and (include_amendments or not record.is_amended)
        and (since is None or record.filing_date >= since)
    ]
    st.caption(
        f"{len(filtered)} filings match your filters (out of {len(records)} total)."
    )
    if not filtered:
        st.info(
            "No filings match your filters. Try widening the date range or "
            "including amendments."
        )
        return

    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "Form": record.form_type,
                "Filed": record.filing_date.isoformat(),
                "Period": (
                    record.period_of_report.isoformat()
                    if record.period_of_report
                    else "—"
                ),
                "FY": record.effective_fiscal_year,
                "Accession": record.accession_number,
                "Open on SEC": record.sec_url,
            }
            for record in filtered
        ]
    )
    event = st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Open on SEC": st.column_config.LinkColumn(
                "Open on SEC",
                help="Opens the filing in a new tab on sec.gov",
                validate="^https://www\\.sec\\.gov/.*",
                display_text="Open",
            )
        },
    )

    selected = getattr(getattr(event, "selection", None), "rows", [])
    if selected:
        record = filtered[selected[0]]
        st.markdown(
            f"**{record.form_type} filed {record.filing_date.isoformat()} · "
            f"period "
            f"{record.period_of_report.isoformat() if record.period_of_report else '—'}**"
        )
        # A radio instead of st.segmented_control: same UX and it is
        # exercisable from AppTest (the selector never triggers a fetch).
        view = st.radio(
            "View",
            options=["Statements", "Narrative"],
            horizontal=True,
            key=f"filings_view_{ticker}",
        )
        col_load, col_clear = st.columns([1, 1])
        if view == "Statements":
            from backend.services.financial_statement_parser import StatementType

            labels = {
                "Balance Sheet": StatementType.BALANCE_SHEET,
                "Income": StatementType.INCOME_STATEMENT,
                "Cash Flow": StatementType.CASH_FLOW,
            }
            choice = st.radio(
                "Statement type",
                options=list(labels),
                horizontal=True,
                key=f"statement_type_{ticker}",
            )
            statement_type = labels[choice]
            if col_load.button("Load", key="filings_load_statement"):
                preview = render_statement_preview(
                    record, statement_type, load_financial_statement
                )
                if not preview["ok"]:
                    st.warning(preview["message"])
                    if preview["sec_url"]:
                        st.markdown(f"[Open it on SEC EDGAR]({preview['sec_url']})")
                else:
                    st.dataframe(
                        preview["table_rows"], hide_index=True, width="stretch"
                    )
                    st.caption(preview["caption"])
                    if preview["warnings"]:
                        st.caption(preview["warnings"][0])
        else:
            from backend.services.narrative_extractor import SectionType

            section_labels = {
                "Risk Factors": SectionType.RISK_FACTORS,
                "MD&A": SectionType.MD_A,
            }
            section_choice = st.radio(
                "Section",
                options=list(section_labels),
                horizontal=True,
                key=f"filings_section_{ticker}",
            )
            section_type = section_labels[section_choice]
            if col_load.button("Load", key="filings_load_section"):
                key = {
                    "ticker": ticker,
                    "cik": getattr(record, "cik", ""),
                    "accession_number": getattr(record, "accession_number", ""),
                    "primary_document": getattr(record, "primary_document", None),
                    "form_type": getattr(record, "form_type", ""),
                    "filing_date": getattr(record, "filing_date", None),
                    "period_of_report": getattr(record, "period_of_report", None),
                    "sec_url": getattr(record, "sec_url", None),
                }
                preview = _load_narrative_cached(
                    tuple(sorted(key.items())), section_type.value
                )
                if not preview["ok"]:
                    st.warning(preview["message"])
                    if preview["sec_url"]:
                        st.markdown(f"[Open it on SEC EDGAR]({preview['sec_url']})")
                else:
                    st.markdown(
                        f"**{preview['title']}** — {preview['word_count']:,} words · "
                        f"{preview['source_label']}"
                    )
                    if preview["word_count"] > 5000:
                        with st.expander("Show full section"):
                            st.markdown(preview["text"])
                    else:
                        st.markdown(preview["text"])
                    st.caption(
                        f"Source: SEC EDGAR · Section: {section_type.label} · "
                        f"Extraction: {preview['source']} · Cached locally"
                    )
                    ibr = next(
                        (
                            w
                            for w in preview["warnings"]
                            if "by reference" in w.lower() or "incorporat" in w.lower()
                        ),
                        None,
                    )
                    if ibr:
                        st.info(
                            f"{ibr} "
                            f"[Open the filing on SEC EDGAR]"
                            f"({preview['sec_url'] or '#'})"
                        )
                    elif preview["warnings"]:
                        st.caption(preview["warnings"][0])
        if col_clear.button("Clear cache", key="filings_clear_cache"):
            from backend.services.filing_fetcher import FilingFetcher

            removed = FilingFetcher().clear_cache()
            st.success(f"Cache cleared ({removed} files).")
    else:
        st.caption(
            "Select a row to preview its balance sheet, or click 'Open' to "
            "view the original on SEC EDGAR."
        )


def _render_compact(ticker: str) -> None:
    rows = load_fundamentals(ticker)
    if not rows:
        _render_missing_fundamentals(ticker)
        return
    quote = load_quote(ticker)
    view = run_methodologies(ticker, rows, quote["price"], quote["market_cap"])
    st.markdown(f"**{ticker}** — Lynch category: {view.category or '—'}")
    st.dataframe(view.table, width="stretch", hide_index=True)


def _price_header(ticker: str, rows: list, quote: dict) -> None:
    """Pinned price/market-cap/sector header, visible across all tabs.

    The quote comes from the cached in-memory price service (never
    persisted); a missing price renders "—" without breaking the page.
    """
    price = quote.get("price")
    market_cap = quote.get("market_cap")
    sector = getattr(rows[0], "sector", None) if rows else None
    st.markdown(f"**{ticker}**")
    col1, col2, col3 = st.columns(3)
    col1.metric("Price", f"${price:,.2f}" if price is not None else "—")
    col2.metric(
        "Market Cap",
        abbreviate_number(market_cap) if market_cap is not None else "—",
    )
    col3.metric("Sector", sector or "—")
    st.divider()


def _overview(rows, quote: dict, view) -> None:
    latest = rows[0]
    metric_row(
        [
            ("Price", fmt_or_dash(quote["price"])),
            ("Market Cap", fmt_money_short(quote["market_cap"])),
            ("Sector", latest.sector or "—"),
            ("Lynch category", view.category or "—"),
        ]
    )
    st.caption(
        f"Latest fiscal year: FY{latest.fiscal_year} · "
        f"{len(rows)} years of fundamentals"
    )
    st.subheader("Disagreement summary")
    if view.agreement:
        st.info("All recorded methodologies agree on this company.")
    else:
        for line in view.family_lines:
            st.markdown(f"- {line}")
        if view.explanation:
            st.caption(view.explanation)
        if view.consensus:
            st.caption(view.consensus)
        for line in view.reason_lines:
            st.markdown(f"- {line}")


def _methodologies(view) -> None:
    st.dataframe(view.table, width="stretch", hide_index=True)
    for detail in view.details:
        title = f"{detail['methodology']} — {detail['verdict']} ({detail['family']})"
        with st.expander(title):
            metric_row(
                [
                    ("Verdict", detail["verdict"]),
                    ("Score", fmt_or_dash(detail["score"])),
                    ("Confidence", detail["confidence"]),
                ]
            )
            if detail.get("category"):
                st.caption(f"Lynch category: {detail['category']}")
            outcomes = detail.get("rule_outcomes") or {}
            if outcomes:
                st.dataframe(
                    [
                        {"Rule": rule_id, "Outcome": outcome}
                        for rule_id, outcome in outcomes.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
            metrics = {
                key: value
                for key, value in (detail.get("metrics") or {}).items()
                if key != "rule_outcomes"
            }
            if metrics:
                st.dataframe(
                    [
                        {
                            "Metric": key,
                            "Value": (
                                "—"
                                if value is None
                                else str(value)
                                if not isinstance(value, (int, float))
                                or isinstance(value, bool)
                                else f"{value:,.2f}"
                            ),
                        }
                        for key, value in metrics.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
            for reason in detail.get("reasons") or []:
                st.markdown(f"- {reason}")
            for flag in detail.get("red_flags") or []:
                st.markdown(f"- **{flag}**")


def _dcf_panel(dcf) -> None:
    st.warning(DCF_DISCLAIMER)
    st.caption(f"Variant: **{dcf.variant_label}**")
    if dcf.is_insufficient:
        st.metric("Verdict", "INSUFFICIENT_DATA")
        for reason in dcf.reasons:
            st.markdown(f"- {reason}")
        if dcf.missing_inputs:
            st.caption("Missing: " + ", ".join(dcf.missing_inputs))
        return
    metric_row(
        [
            ("Intrinsic value", fmt_or_dash(dcf.intrinsic_value_per_share)),
            ("Current price", fmt_or_dash(dcf.current_price)),
            ("Margin of safety", format_pct(dcf.margin_of_safety)),
            ("Verdict", dcf.verdict),
        ]
    )
    with st.expander("Assumptions"):
        st.markdown(
            f"- {dcf.discount_label}: {format_pct(dcf.discount_rate)}\n"
            f"- {dcf.base_text}: {fmt_or_dash(dcf.base_value)}\n"
            f"- Growth years 1-5: {format_pct(dcf.growth_1_5)}\n"
            f"- Growth years 6-10: {format_pct(dcf.growth_6_10)}\n"
            f"- Terminal growth: {format_pct(dcf.terminal_growth)}"
        )
    if dcf.sensitivity_rows:
        st.markdown("**Sensitivity (intrinsic value per share)**")
        st.dataframe(dcf.sensitivity_rows, width="stretch", hide_index=True)
    with st.expander("Notes"):
        for reason in dcf.reasons:
            st.markdown(f"- {reason}")


def _historical(ticker: str) -> None:
    data = load_historical_valuation(ticker)
    if not data:
        st.info("No historical valuation data for this ticker.")
        return
    pe_rows = [
        {"Fiscal year": row["fiscal_year"], "P/E": row["pe_ratio"]}
        for row in sorted(data, key=lambda r: r["fiscal_year"])
        if row.get("pe_ratio") is not None
    ]
    fcf_rows = [
        {
            "Fiscal year": row["fiscal_year"],
            "FCF Yield %": (row["fcf_yield"] or 0.0) * 100.0,
        }
        for row in sorted(data, key=lambda r: r["fiscal_year"])
        if row.get("fcf_yield") is not None
    ]
    if not pe_rows and not fcf_rows:
        st.info("Not enough historical prices for the chart.")
        return
    col1, col2 = st.columns(2)
    with col1:
        if pe_rows:
            st.caption("P/E by fiscal year")
            st.line_chart(pe_rows, x="Fiscal year", y="P/E")
    with col2:
        if fcf_rows:
            st.caption("FCF yield by fiscal year (%)")
            st.line_chart(fcf_rows, x="Fiscal year", y="FCF Yield %")


def _financials(ticker: str) -> None:
    """Every FDB fact for the company: one row per concept, one column/year."""
    from backend.services.financials_view_service import filter_rows, table_rows

    st.caption(
        "Fiscal data from Financial-DataBase — every fact stored for the "
        "company (all XBRL concepts), not just the mapped fields."
    )
    col1, col2 = st.columns([2, 2])
    with col1:
        period = st.radio(
            "Fiscal period",
            ["FY", "Q1", "Q2", "Q3", "Q4"],
            horizontal=True,
            key=f"financials_period_{ticker}",
        )
    with col2:
        max_years = int(
            st.number_input(
                "Show last N years",
                min_value=1,
                max_value=20,
                value=10,
                step=1,
                key=f"financials_years_{ticker}",
            )
        )

    view, report, alerts = _load_financials_cached(ticker, period, max_years)
    if view is None:
        st.info(
            "No financial facts stored for this company (or the demo fixture "
            "does not cover this period)."
        )
        return

    all_rows = view.balance_sheet + view.income_statement + view.cash_flow + view.other
    units = sorted({row.unit for row in all_rows if row.unit})
    col3, col4 = st.columns([2, 3])
    with col3:
        selected_units = set(
            st.multiselect(
                "Unit",
                units,
                default=units,
                key=f"financials_units_{ticker}",
            )
        )
    with col4:
        query = st.text_input(
            "Search concepts",
            placeholder="e.g. cash, revenue, NetIncomeLoss",
            key=f"financials_search_{ticker}",
        )

    st.caption(
        f"{len(all_rows)} concepts across {len(view.years)} years · "
        f"{view.unmatched_count} in Other"
    )
    for warning in view.extraction_warnings:
        st.caption(warning)

    if report is not None:
        from backend.services.financial_insights_service import insight_rows

        with st.expander("Summary", expanded=True):
            dataframe_with_download(
                insight_rows(report),
                f"{ticker}_insights.csv",
                f"financials_insights_{ticker}",
            )
        st.caption(
            f"Computed from Financial-DataBase facts · {view.fiscal_period} "
            f"data · Last {len(view.years)} years"
        )

    buckets = [
        ("Balance Sheet", view.balance_sheet),
        ("Income Statement", view.income_statement),
        ("Cash Flow", view.cash_flow),
        ("Other", view.other),
    ]
    sub_tabs = st.tabs([label for label, _ in buckets])
    for sub_tab, (label, bucket) in zip(sub_tabs, buckets):
        with sub_tab:
            rows = filter_rows(bucket, query=query, units=selected_units)
            dataframe_with_download(
                table_rows(rows, view.years),
                f"{ticker}_{label.lower().replace(' ', '_')}.csv",
                f"financials_{label}_{ticker}",
            )
    st.caption(
        "Source: Financial-DataBase (SEC EDGAR) · Fiscal period: "
        f"{view.fiscal_period} · Values preserve the original filing format."
    )
    # Deterministic alerts (same facts as the tables/insights) in the sidebar,
    # always visible while the user browses the Financials tab.
    _alerts_sidebar(alerts)


def _alerts_sidebar(alerts) -> None:
    """Render the alerts report in the sidebar (no custom HTML/CSS)."""
    with st.sidebar.expander("Alerts", expanded=True):
        if alerts is None:
            st.caption("No alerts available for this company.")
            return
        if not alerts.alerts:
            st.success("No alerts.")
        for alert in alerts.alerts:
            evidence = " · ".join(
                f"{key}: {value}" for key, value in alert.evidence.items()
            )
            body = f"{alert.title}\n\n{alert.message}"
            if evidence:
                body += f"\n\n{evidence}"
            if alert.severity == "CRITICAL":
                st.error(f"🔴 CRITICAL — {body}")
            elif alert.severity == "WARNING":
                st.warning(f"🟠 WARNING — {body}")
            else:
                st.info(f"🔵 INFO — {body}")
        if alerts.rules_skipped:
            st.caption(f"{alerts.rules_skipped} rules skipped (insufficient data).")


def _raw(ticker: str) -> None:
    from ui.services import get_analysis_service

    try:
        result = get_analysis_service().analyze(ticker)
    except Exception as exc:  # noqa: BLE001 — analytics failure must not crash the page
        st.error(f"Metrics analysis failed: {exc}")
        return
    if not result:
        st.info("No analytics metrics for this ticker.")
        return
    rows = [
        {
            "Metric": key,
            "Value": _format_metric(value),
        }
        for key, value in sorted(result.items())
        if not isinstance(value, (dict, list))
    ]
    dataframe_with_download(rows, f"{ticker}_metrics.csv", f"raw_{ticker}")


def _format_metric(value) -> str:
    """Metrics tables are string columns: Arrow must never guess types."""
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return f"{value:,.2f}"


main()
