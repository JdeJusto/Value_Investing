"""Shared adapter for the Streamlit UI: methodology + DCF results as data.

The UI is a view layer: this module runs the same methodology registry and
DCF evaluator the CLI uses and returns plain dataclasses/dicts that are easy
to render (``st.dataframe``) and to unit-test. No analysis logic lives here —
it only orchestrates existing pieces and formats their output.

Prices come from the injected price service (the real ``PriceService`` or a
stub) and are never persisted.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from backend.methodologies.registry import discover, registry
from backend.portfolio.allocation import (
    overconcentration,
    risk_concentration,
    sector_exposure,
)
from backend.portfolio.performance import portfolio_performance
from backend.services.screener_filters import is_investable_company
from backend.valuation.dcf import DCFValuation

#: Human labels for the DCF variants. Mirrors ``cli/commands/dcf.py`` on
#: purpose: the UI must not import a CLI module (backend -> cli is backwards).
VARIANT_LABELS = {
    "standard": "standard DCF (free cash flow)",
    "reit": "REIT — funds from operations",
    "ddm_financial": "financial — dividend discount model",
    "ddm_financial_two_stage": "financial — two-stage dividend discount model",
    "hyper_growth": "hyper-growth — observed positive FCF",
}

BASE_LABELS = {
    "standard": "FCF base",
    "reit": "FFO base",
    "ddm_financial": "Dividend per share",
    "ddm_financial_two_stage": "Dividend per share",
    "hyper_growth": "Normalized FCF base",
}

DASH = "—"


def fmt_or_dash(value: Any, digits: int = 2, percent: bool = False) -> str:
    """Format a number for display; ``None`` becomes an em dash, never 0."""
    if value is None:
        return DASH
    if percent:
        return f"{value:.{digits}%}"
    return f"{value:,.{digits}f}"


def fmt_money_short(value: Any) -> str:
    """Compact money for headlines: $1.40T / $23.5B / $980.0M; None -> dash."""
    if value is None:
        return DASH
    magnitude = abs(value)
    if magnitude >= 1e12:
        return f"${value / 1e12:,.2f}T"
    if magnitude >= 1e9:
        return f"${value / 1e9:,.1f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value:,.0f}"


class _Prices:
    """Adapter so a methodology can ask for prices without knowing PriceService."""

    def __init__(self, price, market_cap=None):
        self._price = price
        self._market_cap = market_cap

    def get_current_price(self, ticker):
        return self._price

    def get_market_cap(self, ticker):
        return self._market_cap


@dataclass
class MethodologiesView:
    """Everything the UI needs for the side-by-side methodology panels."""

    ticker: str
    table: list[dict[str, Any]] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    agreement: bool = True
    family_lines: list[str] = field(default_factory=list)
    explanation: str | None = None
    consensus: str | None = None
    reason_lines: list[str] = field(default_factory=list)
    category: str | None = None


@dataclass
class DCFView:
    """Everything the UI needs for the DCF panel."""

    ticker: str
    verdict: str
    variant: str
    variant_label: str
    intrinsic_value_per_share: float | None
    current_price: float | None
    margin_of_safety: float | None
    discount_label: str
    discount_rate: float | None
    base_text: str
    base_value: float | None
    growth_1_5: float | None
    growth_6_10: float | None
    terminal_growth: float
    shares_outstanding: float | None
    sensitivity_rows: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    is_insufficient: bool = False


def build_methodologies_view(ticker: str, results: list[Any]) -> MethodologiesView:
    """Pure transformation: evaluated MethodologyResults -> view data."""
    table: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    category: str | None = None
    for result in results:
        metrics = dict(result.metrics or {})
        key_reason = result.reasons[0] if result.reasons else ""
        table.append(
            {
                "Methodology": result.methodology,
                "Family": result.family,
                "Verdict": result.verdict.value,
                "Score": fmt_or_dash(result.score, 2),
                "Confidence": result.confidence.value,
                "Key reason": key_reason,
            }
        )
        details.append(
            {
                "methodology": result.methodology,
                "family": result.family,
                "verdict": result.verdict.value,
                "score": result.score,
                "confidence": result.confidence.value,
                "category": metrics.get("lynch_category_label"),
                "rule_outcomes": metrics.get("rule_outcomes", {}),
                "metrics": metrics,
                "reasons": list(result.reasons),
                "red_flags": list(result.red_flags),
            }
        )
        if result.methodology == "lynch_garp":
            category = metrics.get("lynch_category_label")
    agreement, family_lines, explanation, consensus = _disagreement_summary(results)
    reason_lines = [
        f"{result.methodology} ({result.verdict.value}): "
        + "; ".join(result.reasons[:2])
        for result in results
    ]
    return MethodologiesView(
        ticker=ticker,
        table=table,
        details=details,
        agreement=agreement,
        family_lines=family_lines,
        explanation=explanation,
        consensus=consensus,
        reason_lines=reason_lines,
        category=category,
    )


def disagreement_narrative(results: list[Any]) -> dict[str, str]:
    """Honest narrative for a disagreement: explanation + consensus.

    The long value-vs-quality paragraph is printed only when the pattern
    really is "value rejects what quality rewards" (a deep-value member
    says AVOID and a quality member says BUY). Anything else gets a neutral
    line: the families answer different questions. It never declares a
    winner.
    """
    value_members = [
        result
        for result in results
        if "VALUE" in result.family.upper() or "DEEP" in result.family.upper()
    ]
    quality_members = [
        result
        for result in results
        if "QUALITY" in result.family.upper()
        or "COMPOUNDER" in result.family.upper()
        or "DCA" in result.family.upper()
    ]
    value_rejects = any(r.verdict.value == "AVOID" for r in value_members)
    quality_buys = any(r.verdict.value == "BUY" for r in quality_members)
    if value_members and quality_members and value_rejects and quality_buys:
        value_names = ", ".join(m.methodology for m in value_members)
        quality_names = ", ".join(m.methodology for m in quality_members)
        explanation = (
            f"Why the families disagree: the value screen(s) ({value_names}) "
            "judge price against assets/earnings and require a safety margin, "
            "so an expensive or levered balance sheet vetoes them. The "
            f"quality screen(s) ({quality_names}) reward durable profitability "
            "and business strength without requiring a cheap price — exactly "
            "where a strong-but-expensive company splits them."
        )
    else:
        explanation = (
            "The methodologies answer different questions (price vs quality "
            "vs growth); see the family lines and reasons below."
        )
    buys = sum(1 for result in results if result.verdict.value == "BUY")
    if buys == 0:
        consensus = (
            "No methodology gives BUY; the consensus is between rejection and hold."
        )
    elif buys == len(results):
        consensus = "All methodologies give BUY."
    else:
        consensus = (
            f"{buys} of {len(results)} methodologies give BUY; no single "
            "winner is declared."
        )
    return {"explanation": explanation, "consensus": consensus}


def _disagreement_summary(
    results: list[Any],
) -> tuple[bool, list[str], str | None, str | None]:
    """Group verdicts by family and explain the conflict (never a winner).

    Same logic as the CLI's ``compare-methodologies`` summary, as pure data.
    """
    if len(results) < 2:
        return True, [], "Only one methodology is registered.", None
    if len({result.verdict.value for result in results}) == 1:
        return True, [], None, None
    families: dict[str, list[Any]] = {}
    for result in results:
        families.setdefault(result.family, []).append(result)
    family_lines = [
        f"{family} → "
        + ", ".join(
            f"{member.methodology}={member.verdict.value}" for member in members
        )
        for family, members in sorted(families.items())
    ]
    narrative = disagreement_narrative(results)
    return (
        False,
        family_lines,
        narrative["explanation"],
        narrative["consensus"],
    )


def build_dcf_view(result: Any) -> DCFView:
    """Pure transformation: a DCFResult -> view data."""
    variant = getattr(result, "variant", "standard")
    is_ddm = variant.startswith("ddm_financial")
    base_label = BASE_LABELS.get(variant, "FCF base")
    if is_ddm:
        base_text = base_label  # a per-share value, not an average base
    elif result.fcf_years is None:
        base_text = base_label
    elif result.fcf_years >= 3:
        base_text = f"{base_label} (3y avg)"
    elif result.fcf_years == 2:
        base_text = f"{base_label} (2y avg)"
    else:
        base_text = f"{base_label} (1y)"
    return DCFView(
        ticker=result.ticker,
        verdict=result.verdict,
        variant=variant,
        variant_label=VARIANT_LABELS.get(variant, variant),
        intrinsic_value_per_share=result.intrinsic_value_per_share,
        current_price=result.current_price,
        margin_of_safety=result.margin_of_safety,
        discount_label="Cost of equity" if is_ddm else "WACC",
        discount_rate=result.wacc,
        base_text=base_text,
        base_value=result.fcf_base,
        growth_1_5=result.growth_1_5,
        growth_6_10=result.growth_6_10,
        terminal_growth=result.terminal_growth,
        shares_outstanding=result.shares_outstanding,
        sensitivity_rows=_sensitivity_rows(result),
        reasons=list(result.reasons),
        missing_inputs=list(result.missing_inputs),
        is_insufficient=result.verdict == "INSUFFICIENT_DATA",
    )


def _sensitivity_rows(result: Any) -> list[dict[str, Any]]:
    """3x3 WACC x growth grid as rows of dicts for st.dataframe."""
    if not result.sensitivity or result.wacc is None or result.growth_1_5 is None:
        return []
    rows: list[dict[str, Any]] = []
    for dw in (-0.02, 0.0, 0.02):
        wacc = result.wacc + dw
        row: dict[str, Any] = {"WACC \\ Growth": f"{wacc:.2%}"}
        for dg in (-0.02, 0.0, 0.02):
            value = result.sensitivity.get((wacc, result.growth_1_5 + dg))
            label = "g-2%" if dg < 0 else ("g" if dg == 0 else "g+2%")
            row[label] = value
        rows.append(row)
    return rows


def run_methodologies(
    ticker: str, rows: list[Any], price: float | None, market_cap: float | None = None
) -> MethodologiesView:
    """Evaluate every registered methodology on one ticker (thin orchestration)."""
    discover()
    prices = _Prices(price, market_cap)
    results = []
    for name in registry.list():
        methodology = registry.get(name)
        if methodology is None:
            continue
        results.append(methodology.evaluate(ticker, rows, prices))
    return build_methodologies_view(ticker, results)


def run_dcf(ticker: str, rows: list[Any], price_service: Any) -> DCFView:
    """Evaluate the not-from-canon DCF and shape it for the UI."""
    return build_dcf_view(DCFValuation().evaluate(ticker, rows, price_service))


#: A sector above this weight triggers a concentration warning.
SECTOR_CONCENTRATION_THRESHOLD = 0.40


@dataclass
class PortfolioView:
    """Everything the UI needs for the read-only portfolio page."""

    name: str
    is_empty: bool
    positions: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    sector_exposure: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def build_portfolio_view(portfolio: Any, sectors: dict | None = None) -> PortfolioView:
    """Pure transformation: a Portfolio -> portfolio page view data.

    Read-only: reuses the pure performance/allocation functions; it never
    refreshes or saves prices (the CLI owns that side effect).
    """
    sectors = sectors or {}
    performance = portfolio_performance(portfolio)
    open_positions = [p for p in portfolio.positions if p.is_open]
    rows: list[dict[str, Any]] = []
    for position in open_positions:
        has_price = bool(position.current_price and position.current_price > 0)
        rows.append(
            {
                "Ticker": position.ticker,
                "Shares": position.quantity,
                "Avg Price": fmt_or_dash(position.avg_price),
                "Current Price": (
                    fmt_or_dash(position.current_price) if has_price else DASH
                ),
                "Value": fmt_or_dash(position.market_value) if has_price else DASH,
                "PnL": fmt_or_dash(position.unrealized_pnl) if has_price else DASH,
                "PnL%": (
                    fmt_or_dash(position.unrealized_return, percent=True)
                    if has_price
                    else DASH
                ),
                "Thesis": position.thesis or DASH,
                "Signal": position.signal_at_entry or DASH,
            }
        )
    exposure = sector_exposure(portfolio, sectors, top=50)
    warnings = [
        f"{finding['ticker']} pesa {finding['weight']:.1%} de la cartera (umbral 25%)"
        for finding in overconcentration(portfolio)
    ]
    warnings += [
        f"El sector {row['sector']} pesa {row['weight']:.1%} de la cartera (umbral 40%)"
        for row in exposure
        if row["sector"] != "N/A" and row["weight"] > SECTOR_CONCENTRATION_THRESHOLD
    ]
    return PortfolioView(
        name=portfolio.name,
        is_empty=not open_positions,
        positions=rows,
        totals={
            "market_value": performance["market_value"],
            "cost_basis": performance["cost_basis"],
            "unrealized_pnl": performance["unrealized_pnl"],
            "realized_pnl": performance["realized_pnl"],
            "total_pnl": performance["total_pnl"],
            "total_return": performance["total_return"],
        },
        sector_exposure=exposure,
        risk=risk_concentration(portfolio),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Portfolio actions (validated; the UI form and buttons call these)
# ---------------------------------------------------------------------------
class PortfolioActionError(ValueError):
    """A portfolio action that failed validation; the message is user-facing."""


def validate_new_position(
    ticker: str,
    shares: float | None,
    price: float | None,
    entry_date: date | None = None,
    ticker_checker: Any = None,
    today: date | None = None,
) -> str:
    """Validate an add-position input; returns the normalized ticker.

    ``ticker_checker`` is an optional callable that answers "does this ticker
    exist in the fundamentals database?"; when omitted, no existence check is
    performed (graceful fallback).
    """
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise PortfolioActionError("El ticker es obligatorio.")
    if ticker_checker is not None and not ticker_checker(normalized):
        raise PortfolioActionError(
            f"El ticker {normalized} no existe en la base de datos."
        )
    if shares is None or shares <= 0:
        raise PortfolioActionError("Las acciones deben ser mayores que 0.")
    if price is None or price <= 0:
        raise PortfolioActionError("El precio debe ser mayor que 0.")
    reference = today or datetime.now(UTC).date()
    if entry_date is not None and entry_date > reference:
        raise PortfolioActionError("La fecha de entrada no puede ser futura.")
    return normalized


def add_position(
    service: Any,
    ticker: str,
    shares: float | None,
    price: float | None,
    entry_date: date | None = None,
    thesis: str = "",
    signal: str = "",
    ticker_checker: Any = None,
    today: date | None = None,
):
    """Validated add; averages into an existing open position when present."""
    normalized = validate_new_position(
        ticker, shares, price, entry_date, ticker_checker, today
    )
    entry_dt = None
    if entry_date is not None:
        entry_dt = datetime(
            entry_date.year, entry_date.month, entry_date.day, tzinfo=UTC
        )
    return service.add(
        normalized,
        shares,
        price,
        entry_date=entry_dt,
        thesis=thesis,
        signal_at_entry=signal,
    )


def exit_position(
    service: Any, ticker: str, price: float | None, portfolio: Any = None
):
    """Validated exit; returns the closed position (realized PnL recorded)."""
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise PortfolioActionError("El ticker es obligatorio.")
    if price is None or price <= 0:
        raise PortfolioActionError("El precio de salida debe ser mayor que 0.")
    if portfolio is not None:
        position = portfolio.position(normalized)
        if position is None:
            raise PortfolioActionError(f"No hay posición abierta para {normalized}.")
        if position.quantity <= 0:
            raise PortfolioActionError(
                f"{normalized} no tiene acciones; usa Remove en lugar de Exit."
            )
    closed = service.exit(normalized, price)
    if closed is None:
        raise PortfolioActionError(f"No hay posición abierta para {normalized}.")
    return closed


def remove_position(service: Any, ticker: str, portfolio: Any = None):
    """Validated remove (no PnL recorded); returns the removed position."""
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise PortfolioActionError("El ticker es obligatorio.")
    if portfolio is not None and not any(
        p.ticker.upper() == normalized for p in portfolio.positions
    ):
        raise PortfolioActionError(f"No hay posición para {normalized}.")
    removed = service.remove(normalized)
    if removed is None:
        raise PortfolioActionError(f"No hay posición para {normalized}.")
    return removed


# ---------------------------------------------------------------------------
# Daily report parsing (Home page)
# ---------------------------------------------------------------------------
_ALERT_RE = re.compile(
    r"^-\s+\*\*(?P<ticker>[A-Z0-9.\-]+)\*\*\s+—\s+(?P<kind>.*?)\s+"
    r"\(\*(?P<severity>[A-Z]+)\*\):\s+(?P<message>.*)$"
)


def parse_daily_report(text: str) -> dict[str, Any]:
    """Parse a ``daily_*.md`` report into screened rows and alerts.

    Pure function (no filesystem): the Home page and its tests feed it the
    markdown text. Returns ``{"date", "screened", "alerts"}``; both lists are
    empty when the section is missing.
    """
    date: str | None = None
    screened: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    section: str | None = None
    header: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("# ") and date is None:
            parts = line.lstrip("# ").split("—")
            if len(parts) == 2:
                date = parts[1].strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            header = None
            continue
        if section == "screened" and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-", " "} for cell in cells):
                continue
            if header is None:
                header = cells
                continue
            if len(cells) == len(header):
                screened.append(dict(zip(header, cells)))
        elif section == "alerts":
            match = _ALERT_RE.match(line)
            if match:
                alerts.append(match.groupdict())
    return {"date": date, "screened": screened, "alerts": alerts}


def parse_daily_report_file(path: str | Path) -> dict[str, Any]:
    """Read a report file and parse it (``filename`` added to the result)."""
    file_path = Path(path)
    parsed = parse_daily_report(file_path.read_text(encoding="utf-8"))
    parsed["filename"] = file_path.name
    return parsed


def latest_daily_report(reports_dir: str | Path) -> dict[str, Any] | None:
    """Newest ``daily_*.md`` in ``reports_dir`` parsed, or None."""
    directory = Path(reports_dir)
    if not directory.exists():
        return None
    files = sorted(directory.glob("daily_*.md"))
    if not files:
        return None
    return parse_daily_report_file(files[-1])


def list_reports(reports_dir: str | Path) -> list[dict[str, Any]]:
    """Every ``*.md`` report with date/size/mtime, newest first."""
    directory = Path(reports_dir)
    if not directory.exists():
        return []
    entries = []
    for path in directory.glob("*.md"):
        stat = path.stat()
        entries.append(
            {
                "filename": path.name,
                "date": datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime(
                    "%Y-%m-%d"
                ),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "path": str(path),
            }
        )
    return sorted(entries, key=lambda entry: entry["mtime"], reverse=True)


def parse_universe_tickers(
    csv_text: str, universes: list[str] | tuple[str, ...]
) -> list[str]:
    """Tickers from the master-universe CSV for the selected source indexes.

    Pure function: ``universes`` empty or containing "All" means every row.
    """
    import csv
    import io

    selected = {universe.upper() for universe in universes}
    include_all = not selected or "ALL" in selected
    tickers = set()
    for row in csv.DictReader(io.StringIO(csv_text)):
        sources = {
            source.strip().upper()
            for source in (row.get("source_index") or "").split(",")
        }
        if include_all or sources & selected:
            ticker = (row.get("ticker") or "").strip().upper()
            if ticker:
                tickers.add(ticker)
    return sorted(tickers)


def apply_numeric_filters(
    rows: list[dict[str, Any]],
    *,
    mcap_min: float = 0.0,
    mcap_max: float = 0.0,
    pe_max: float = 0.0,
    roe_min: float = 0.0,
    fcf_min: float = 0.0,
) -> list[dict[str, Any]]:
    """Filter screener rows by market cap (B), P/E, ROE and FCF yield.

    A disabled filter (<= 0) keeps rows with missing values; an active filter
    drops rows whose metric is missing (no data cannot prove the filter).
    """

    def keep(row: dict[str, Any]) -> bool:
        mcap = row.get("market_cap")
        per = row.get("per")
        roe = row.get("roe")
        fcf = row.get("fcf_yield")
        if mcap_min and (mcap is None or mcap < mcap_min * 1e9):
            return False
        if mcap_max and (mcap is None or mcap > mcap_max * 1e9):
            return False
        if pe_max and (per is None or per > pe_max):
            return False
        if roe_min and (roe is None or roe < roe_min):
            return False
        return not (fcf_min and (fcf is None or fcf < fcf_min))

    return [row for row in rows if keep(row)]


def validate_screener_range(mcap_min: float, mcap_max: float) -> str | None:
    """Error message when the market-cap range is impossible, else None."""
    if mcap_max and mcap_min > mcap_max:
        return "El market cap mínimo no puede superar el máximo."
    return None


#: Initial guess until a real run has been measured.
DEFAULT_SCREENER_SECONDS_PER_TICKER = 1.8


def screener_estimate(n_tickers: int, per_ticker: float | None = None) -> dict:
    """Estimated screener duration for ``n_tickers``.

    ``per_ticker`` is the measured seconds/ticker from the last run; when it
    is missing or non-positive the initial guess is used and
    ``is_initial`` is True.
    """
    is_initial = per_ticker is None or per_ticker <= 0
    speed = DEFAULT_SCREENER_SECONDS_PER_TICKER if is_initial else float(per_ticker)
    seconds = speed * max(int(n_tickers), 0)
    if seconds < 120:
        text = f"~{seconds:.0f} s"
    else:
        text = f"~{seconds / 60:.0f} min"
    return {
        "seconds": seconds,
        "text": text,
        "per_ticker": speed,
        "is_initial": is_initial,
    }


def refresh_portfolio_prices(portfolio: Any, price_service: Any) -> dict[str, dict]:
    """Current price per open position vs the stored one; persists nothing.

    Returns ``{ticker: {"stored", "new", "delta_pct"}}``. Tickers whose fetch
    fails (or returns a non-positive price) are omitted — no fabricated price.
    """
    refreshed: dict[str, dict] = {}
    for position in portfolio.positions:
        if not position.is_open:
            continue
        try:
            price = price_service.get_current_price(position.ticker)
        except Exception:  # noqa: BLE001 — a failed fetch is not a crash
            price = None
        if price is None or price <= 0:
            continue
        stored = float(position.current_price or 0.0)
        delta = (float(price) - stored) / stored if stored else None
        refreshed[position.ticker] = {
            "stored": stored,
            "new": float(price),
            "delta_pct": delta,
        }
    return refreshed


def save_portfolio_prices(
    portfolio: Any, prices: dict[str, dict], repository: Any
) -> int:
    """Persist refreshed prices through the repository; returns how many.

    Only tickers present in ``prices`` are touched; the portfolio object is
    updated in place and saved atomically by the repository. This is the only
    path that writes prices, and the UI calls it from an explicit button.
    """
    updated = 0
    for ticker, data in prices.items():
        position = portfolio.position(ticker)
        if position is None:
            continue
        position.current_price = float(data["new"])
        updated += 1
    if updated:
        repository.save(portfolio)
    return updated


#: Bounded workers for the screener enrichment. The per-ticker cost is
#: dominated by the fundamentals read (one DB round trip), so a small pool
#: gives a near-linear speedup without hammering the database.
ENRICHMENT_WORKERS = 4


def enrich_rows(
    rows: list[dict],
    methodology: str,
    sectors: dict,
    load_fundamentals,
    run_methodologies,
    workers: int = ENRICHMENT_WORKERS,
    include_funds: bool = False,
) -> list[dict]:
    """Enrich screener rows with verdict, score and category (parallel).

    ``load_fundamentals`` and ``run_methodologies`` are injected so the UI
    can pass its cached loaders and tests can pass stubs. Results keep the
    input order; a ticker whose loader or evaluation fails degrades to an
    empty verdict instead of breaking the whole batch. The enrichment never
    touches the network itself (prices come from the screened rows), so no
    per-batch Yahoo preflight is involved.
    """

    def enrich_one(row: dict) -> dict | None:
        ticker = row["ticker"]
        verdict = score = category = None
        try:
            fundamentals = load_fundamentals(ticker)
        except Exception:  # noqa: BLE001 — one bad ticker must not break the batch
            fundamentals = None
        if not include_funds and not is_investable_company(
            fundamentals[0] if fundamentals else None,
            fundamentals,
            name=row.get("name"),
        ):
            return None
        if fundamentals:
            try:
                view = run_methodologies(ticker, fundamentals, row.get("price"))
            except Exception:  # noqa: BLE001 — same: degrade this row only
                view = None
            if view is not None:
                detail = next(
                    (d for d in view.details if d["methodology"] == methodology),
                    None,
                )
                if detail:
                    verdict = detail["verdict"]
                    score = detail["score"]
                category = view.category
        return {
            "Ticker": ticker,
            "Name": row.get("name"),
            "Sector": sectors.get(ticker),
            "Price": row.get("price"),
            "P/E": row.get("per"),
            "FCF Yield": row.get("fcf_yield"),
            "ROE": row.get("roe"),
            "Verdict": verdict,
            "Score": score,
            "Category": category,
        }

    if workers <= 1 or len(rows) <= 1:
        enriched = [enrich_one(row) for row in rows]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            enriched = list(pool.map(enrich_one, rows))
    return [row for row in enriched if row is not None]


def render_statement_preview(
    record: Any, statement_type: Any, loader
) -> dict[str, Any]:
    """Pure view-model for the Filings tab's statement preview.

    ``loader`` is injected (``load_financial_statement`` in the page, a stub
    in tests) so the whole preview can be asserted without Streamlit. The
    page converts the returned dict into st.dataframe / st.caption /
    st.warning; nothing here touches the network.
    """
    label = statement_type.label
    period = (
        record.period_of_report.isoformat()
        if getattr(record, "period_of_report", None)
        else "—"
    )
    header = (
        f"{record.form_type} filed {record.filing_date.isoformat()} · period {period}"
    )
    sec_url = getattr(record, "sec_url", None)
    statement = loader(record, statement_type)
    if statement is None:
        return {
            "ok": False,
            "header": header,
            "table_rows": [],
            "caption": "",
            "warnings": [],
            "message": (
                f"This filing does not contain a {label} statement "
                "(or it could not be extracted)."
            ),
            "sec_url": sec_url,
        }
    return {
        "ok": True,
        "header": header,
        "table_rows": statement.as_rows(),
        "caption": (
            f"Source: SEC EDGAR · Statement: {label} · "
            f"Extraction: {statement.source} · Cached locally"
        ),
        "warnings": list(statement.extraction_warnings),
        "message": None,
        "sec_url": sec_url,
    }
