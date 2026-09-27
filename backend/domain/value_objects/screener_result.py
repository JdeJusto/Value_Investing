from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScreenerRow:
    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None
    market_cap: Optional[float] = None
    per: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    roic: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    fcf_yield: Optional[float] = None
    ev_ebit: Optional[float] = None
    debt_to_equity: Optional[float] = None
    revenue_growth: Optional[float] = None
    fcf: Optional[float] = None
    shares_outstanding: Optional[int] = None
    score: Optional[float] = None
    extra: dict = field(default_factory=dict)
