from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
