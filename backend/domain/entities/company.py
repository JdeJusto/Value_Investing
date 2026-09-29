from dataclasses import dataclass


@dataclass
class Company:
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
