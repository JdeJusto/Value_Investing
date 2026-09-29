from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScreenerRow:
    ticker: str
    name: str | None = None
    price: float | None = None
    market_cap: float | None = None
    per: float | None = None
    pb: float | None = None
    roe: float | None = None
    roic: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    fcf_yield: float | None = None
    ev_ebit: float | None = None
    debt_to_equity: float | None = None
    revenue_growth: float | None = None
    fcf: float | None = None
    shares_outstanding: int | None = None
    score: float | None = None
    extra: dict = field(default_factory=dict)
