from dataclasses import dataclass
from typing import Optional


@dataclass
class Company:
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
