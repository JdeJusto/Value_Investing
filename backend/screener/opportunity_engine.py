"""Opportunity detection: the alpha core of the screener.

Each opportunity type encodes a classic investing situation with
deterministic, published conditions. A company can trigger several
types; the strongest match is reported first.
"""

from typing import Optional

# --- Undervalued quality ---
UNDERVALUED_MIN_BUFFETT = 70.0
UNDERVALUED_MIN_MARGIN = 0.15

# --- Compounders ---
COMPOUNDER_MIN_ROIC = 0.15
COMPOUNDER_MIN_CAGR = 0.05

# --- Turnarounds ---
TURNAROUND_MIN_MARGIN_TREND = 0.002  # percentage points per year
TURNAROUND_MAX_DEBT_TREND = -0.05
TURNAROUND_MIN_EARNINGS_RECOVERY = 0.20

# --- Special situations ---
SPECIAL_MAX_PRICE_BOOK = 0.80
SPECIAL_MIN_VOLATILITY = 0.50
SPECIAL_ABNORMAL_EARNINGS_SHIFT = 0.50


def _quality(item: dict, key: str, default=None) -> Optional[float]:
    return (item.get("quality_metrics") or {}).get(key, default)


def _moat_type(item: dict) -> str:
    return (item.get("moat_analysis") or {}).get("moat_type", "NONE")


def _moat_strong_enough(item: dict) -> bool:
    return _moat_type(item) in ("STRONG", "MODERATE")


def _confidence(item: dict) -> str:
    return (item.get("composite_score") or {}).get("confidence", "LOW")


# ----------------------------------------------------------------------
def undervalued_quality(item: dict) -> Optional[dict]:
    """High quality at a discount to DCF value."""
    buffett = item.get("buffett_score")
    margin = item.get("dcf_margin_of_safety")
    if (
        buffett is not None
        and buffett >= UNDERVALUED_MIN_BUFFETT
        and _moat_strong_enough(item)
        and margin is not None
        and margin >= UNDERVALUED_MIN_MARGIN
    ):
        reasons = ["Buffett score above 70", f"moat: {_moat_type(item).lower()}"]
        roic = _quality(item, "roic_mean")
        if roic is not None and roic >= 0.12:
            reasons.append(f"ROIC {roic:.0%} on invested capital")
        reasons.append(f"{margin:.0%} margin of safety vs DCF value")
        return {
            "type": "UNDERVALUED_QUALITY",
            "confidence": _confidence(item),
            "reason": reasons,
        }
    return None


def compounders(item: dict) -> Optional[dict]:
    """Sustained high ROIC with steady growth and reinvestment capacity."""
    roic = _quality(item, "roic_mean")
    cagr = _quality(item, "revenue_cagr")
    fcf = _quality(item, "positive_fcf_ratio")
    retained = item.get("quality_metrics", {}).get("retained_earnings_positive")
    if (
        roic is not None
        and roic >= COMPOUNDER_MIN_ROIC
        and cagr is not None
        and cagr >= COMPOUNDER_MIN_CAGR
        and fcf is not None
        and fcf >= 0.8
        and retained
    ):
        reasons = [
            f"sustained ROIC of {roic:.0%}",
            f"revenue growing at {cagr:.0%} CAGR",
            "strong FCF with retained earnings to reinvest",
        ]
        return {
            "type": "COMPOUNDERS",
            "confidence": _confidence(item),
            "reason": reasons,
        }
    return None


def turnarounds(item: dict) -> Optional[dict]:
    """Improving margins, deleveraging and recovering earnings."""
    margin_trend = _quality(item, "gross_margin_trend")
    debt_trend = _quality(item, "debt_trend")
    income_change = _quality(item, "net_income_change")
    if (
        margin_trend is not None
        and margin_trend >= TURNAROUND_MIN_MARGIN_TREND
        and debt_trend is not None
        and debt_trend <= TURNAROUND_MAX_DEBT_TREND
        and income_change is not None
        and income_change >= TURNAROUND_MIN_EARNINGS_RECOVERY
    ):
        reasons = [
            "gross margins improving",
            f"debt-to-equity down {abs(debt_trend):.0%}",
            f"earnings up {income_change:.0%} year over year",
        ]
        return {
            "type": "TURNAROUNDS",
            "confidence": _confidence(item),
            "reason": reasons,
        }
    return None


def special_situations(item: dict) -> Optional[dict]:
    """Basic special situations: deep value, abnormal shifts, volatile quality."""
    reasons: list[str] = []
    found = False

    price = item.get("current_price")
    book_value = _quality(item, "book_value_per_share")
    if price and book_value and book_value > 0:
        if price / book_value <= SPECIAL_MAX_PRICE_BOOK:
            found = True
            reasons.append(f"price {price / book_value:.0%} of book value per share")

    income_change = _quality(item, "net_income_change")
    if (
        income_change is not None
        and abs(income_change) >= SPECIAL_ABNORMAL_EARNINGS_SHIFT
    ):
        found = True
        reasons.append(f"abnormal earnings shift of {income_change:.0%}")

    earnings_cv = _quality(item, "earnings_cv")
    buffett = item.get("buffett_score")
    if (
        earnings_cv is not None
        and earnings_cv >= SPECIAL_MIN_VOLATILITY
        and buffett is not None
        and buffett >= 60
        and _moat_strong_enough(item)
    ):
        found = True
        reasons.append("high earnings volatility with strong fundamentals")

    if found:
        return {
            "type": "SPECIAL_SITUATIONS",
            "confidence": _confidence(item),
            "reason": reasons,
        }
    return None


# ----------------------------------------------------------------------
DETECTORS = (
    undervalued_quality,
    compounders,
    turnarounds,
    special_situations,
)


def detect_opportunities(item: dict) -> list[dict]:
    """All opportunity types that match, strongest first."""
    return [detector(item) for detector in DETECTORS if detector(item) is not None]


def best_opportunity(item: dict) -> Optional[dict]:
    """The most relevant opportunity, or None."""
    opportunities = detect_opportunities(item)
    return opportunities[0] if opportunities else None
