"""Allocation analysis: concentration and sector exposure warnings."""

from collections import Counter

from backend.portfolio.models import Portfolio
from backend.portfolio.performance import position_weight

OVERCONCENTRATION_THRESHOLD = 0.25
RISK_TOP_N = 5
RISK_MAX_TOP_SHARE = 0.60
RISK_MAX_SINGLE_SHARE = 0.30


def overconcentration(
    portfolio: Portfolio, threshold: float = OVERCONCENTRATION_THRESHOLD
) -> list[dict]:
    """Positions whose weight exceeds ``threshold`` of the portfolio."""
    value = sum(p.market_value for p in portfolio.positions if p.is_open)
    findings: list[dict] = []
    for p in portfolio.positions:
        if not p.is_open:
            continue
        weight = position_weight(p, value)
        if weight is not None and weight > threshold:
            findings.append(
                {
                    "ticker": p.ticker,
                    "weight": round(weight, 4),
                    "threshold": threshold,
                }
            )
    return sorted(findings, key=lambda f: f["weight"], reverse=True)


def sector_exposure(
    portfolio: Portfolio, sectors: dict[str, str | None], top: int = 3
) -> list[dict]:
    """Weight per sector; unknown sectors are grouped as 'N/A'."""
    value = sum(p.market_value for p in portfolio.positions if p.is_open)
    exposure: Counter[str] = Counter()
    for p in portfolio.positions:
        if not p.is_open:
            continue
        weight = position_weight(p, value) or 0.0
        exposure[sectors.get(p.ticker) or "N/A"] += weight
    return [
        {"sector": sector, "weight": round(weight, 4)}
        for sector, weight in exposure.most_common(top)
    ]


def risk_concentration(portfolio: Portfolio) -> dict:
    """Single-name and top-N concentration plus a simple HHI score."""
    value = sum(p.market_value for p in portfolio.positions if p.is_open)
    weights = sorted(
        (
            w
            for p in portfolio.positions
            if p.is_open and (w := position_weight(p, value)) is not None
        ),
        reverse=True,
    )
    hhi = sum(w * w for w in weights)
    top_n_share = sum(weights[:RISK_TOP_N])
    largest = weights[0] if weights else 0.0
    return {
        "largest_position_weight": round(largest, 4),
        "top_n_share": round(top_n_share, 4),
        "hhi": round(hhi, 4),
        "single_name_risk": largest > RISK_MAX_SINGLE_SHARE,
        "top_n_risk": top_n_share > RISK_MAX_TOP_SHARE,
    }
