"""Shared adapter for the Streamlit UI: methodology + DCF results as data.

The UI is a view layer: this module runs the same methodology registry and
DCF evaluator the CLI uses and returns plain dataclasses/dicts that are easy
to render (``st.dataframe``) and to unit-test. No analysis logic lives here —
it only orchestrates existing pieces and formats their output.

Prices come from the injected price service (the real ``PriceService`` or a
stub) and are never persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from backend.methodologies.registry import discover, registry
from backend.portfolio.allocation import (
    overconcentration,
    risk_concentration,
    sector_exposure,
)
from backend.portfolio.performance import portfolio_performance
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
    agreement, family_lines, explanation = _disagreement_summary(results)
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
        reason_lines=reason_lines,
        category=category,
    )


def _disagreement_summary(results: list[Any]) -> tuple[bool, list[str], str | None]:
    """Group verdicts by family and explain the conflict (never a winner).

    Same logic as the CLI's ``compare-methodologies`` summary, as pure data.
    """
    if len(results) < 2:
        return True, [], "Only one methodology is registered."
    if len({result.verdict.value for result in results}) == 1:
        return True, [], None
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
    if value_members and quality_members:
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
        explanation = "The methodologies use different lenses; see the reasons below."
    return False, family_lines, explanation


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
    reference = today or datetime.now(timezone.utc).date()
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
            entry_date.year, entry_date.month, entry_date.day, tzinfo=timezone.utc
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
