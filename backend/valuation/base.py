"""Data structures for the ``not-from-canon`` DCF valuation module.

The inputs and outputs of :class:`DCFValuation` are declared here so the
module stays a thin, deterministic function of data plus assumptions. Nothing
in this file touches a network, a database or a price service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The source label that must accompany every DCF output. It is deliberately
#: NOT a methodology name: the module is not part of any book-derived canon.
SOURCE = "not-from-canon"


@dataclass(frozen=True)
class DCFAssumptions:
    """Deterministic, documented constants for the DCF.

    All defaults are adjustable before calling :meth:`DCFValuation.evaluate`
    (e.g. the CLI's ``--wacc``/``--growth``/``--terminal-growth`` flags). See
    ``backend/valuation/README.md`` for the rationale of each constant.
    """

    risk_free_rate: float = 0.04
    equity_risk_premium: float = 0.05
    tax_rate: float = 0.21
    terminal_growth: float = 0.025
    max_growth_years_1_5: float = 0.20
    max_growth_years_6_10: float = 0.10
    # Explicit CLI overrides (None = compute from data).
    wacc_override: float | None = None
    growth_override: float | None = None


@dataclass
class DCFResult:
    """Outcome of a single :meth:`DCFValuation.evaluate` call.

    ``verdict`` is one of ``UNDERVALUED``, ``FAIR``, ``OVERVALUED`` or
    ``INSUFFICIENT_DATA``. ``sensitivity`` maps ``(wacc, growth_1_5)`` to an
    intrinsic value per share (or ``None`` when that cell is not well posed).
    """

    ticker: str
    intrinsic_value_per_share: float | None
    current_price: float | None
    margin_of_safety: float | None  # (intrinsic - price) / intrinsic
    verdict: str
    wacc: float | None
    fcf_base: float | None
    fcf_years: int | None
    growth_1_5: float | None
    growth_6_10: float | None
    terminal_growth: float
    shares_outstanding: float | None
    sensitivity: dict[tuple[float, float], float | None] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    source: str = SOURCE
    #: Which valuation variant produced this result. ``evaluate`` dispatches
    #: on the shared company-type detector: ``standard`` (free cash flow),
    #: ``reit`` (funds from operations), ``ddm_financial`` (dividend discount
    #: model) and ``hyper_growth`` (observed positive FCF years).
    variant: str = "standard"
    #: True when the DDM subtracted preferred dividends from the total
    #: dividend base (financials with no common-only dividend tag).
    preferred_dividend_adjusted: bool = False
