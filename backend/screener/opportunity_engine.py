"""Opportunity detection: the alpha core of the screener.

Each opportunity type encodes a classic investing situation with
deterministic, published conditions. A company can trigger several
types; the strongest match is reported first.
"""


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

# --- Inflection point ---
INFLECTION_MIN_RECOVERY = 0.05

# --- Fundamental acceleration ---
ACCELERATION_MIN_REV_DELTA = 0.02

# --- Quality with trigger ---
QUALITY_WITH_TRIGGER_MIN_BUFFETT = 70.0
QUALITY_TRIGGER_MARGIN = 0.01
QUALITY_TRIGGER_REV_DELTA = 0.01
QUALITY_TRIGGER_ROIC_DELTA = 0.02


def _quality(item: dict, key: str, default=None) -> float | None:
    return (item.get("quality_metrics") or {}).get(key, default)


def _delta(item: dict, key: str) -> float | None:
    return (item.get("delta_metrics") or {}).get(key)


def _moat_type(item: dict) -> str:
    return (item.get("moat_analysis") or {}).get("moat_type", "NONE")


def _moat_strong_enough(item: dict) -> bool:
    return _moat_type(item) in ("STRONG", "MODERATE")


def _confidence(item: dict) -> str:
    return (item.get("composite_score") or {}).get("confidence", "LOW")


# ----------------------------------------------------------------------
def undervalued_quality(item: dict) -> dict | None:
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


def compounders(item: dict) -> dict | None:
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
        and retained is True
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


def turnarounds(item: dict) -> dict | None:
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


def special_situations(item: dict) -> dict | None:
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


def inflection_point(item: dict) -> dict | None:
    """Earnings that turned positive, or revenue growth re-accelerating."""
    deltas = item.get("delta_metrics") or {}
    reasons: list[str] = []

    income_change = _delta(item, "net_income_change")
    if income_change is not None and income_change >= INFLECTION_MIN_RECOVERY:
        reasons.append(f"earnings recovering {income_change:.0%} year over year")

    rev_last = deltas.get("revenue_growth_last")
    rev_prev = deltas.get("revenue_growth_prev")
    if rev_last is not None and rev_prev is not None and rev_prev <= 0 and rev_last > 0:
        reasons.append(
            f"revenue growth turned positive ({rev_last:.0%} vs {rev_prev:.0%})"
        )

    if not reasons:
        return None
    return {
        "type": "INFLECTION_POINT",
        "confidence": _confidence(item),
        "reason": reasons,
    }


def fundamental_acceleration(item: dict) -> dict | None:
    """Top line accelerating while capital efficiency improves."""
    rev_delta = _delta(item, "revenue_growth_delta")
    roic_delta = _delta(item, "roic_delta")
    fcf_ratio = _quality(item, "positive_fcf_ratio")
    if (
        rev_delta is not None
        and rev_delta >= ACCELERATION_MIN_REV_DELTA
        and roic_delta is not None
        and roic_delta >= 0
        and (fcf_ratio is None or fcf_ratio >= 0.7)
    ):
        reasons = [
            f"revenue growth accelerating by {rev_delta*100:.1f}pp",
            f"ROIC improving by {roic_delta*100:.1f}pp",
        ]
        if fcf_ratio is not None:
            reasons.append("cash generation intact")
        return {
            "type": "FUNDAMENTAL_ACCELERATION",
            "confidence": _confidence(item),
            "reason": reasons,
        }
    return None


def quality_with_trigger(item: dict) -> dict | None:
    """A quality business just got a fundamental confirmation signal."""
    buffett = item.get("buffett_score")
    if buffett is None or buffett < QUALITY_WITH_TRIGGER_MIN_BUFFETT:
        return None
    if not _moat_strong_enough(item):
        return None

    margin_delta = _delta(item, "gross_margin_delta")
    rev_delta = _delta(item, "revenue_growth_delta")
    roic_delta = _delta(item, "roic_delta")

    triggers: list[str] = []
    if margin_delta is not None and margin_delta >= QUALITY_TRIGGER_MARGIN:
        triggers.append(f"margin expansion of {margin_delta*100:.1f}pp")
    if rev_delta is not None and rev_delta >= QUALITY_TRIGGER_REV_DELTA:
        triggers.append(f"revenue acceleration of {rev_delta*100:.1f}pp")
    if roic_delta is not None and roic_delta >= QUALITY_TRIGGER_ROIC_DELTA:
        triggers.append(f"ROIC improvement of {roic_delta*100:.1f}pp")

    if not triggers:
        return None
    reasons = [
        f"quality business (Buffett {buffett:.0f}, moat {_moat_type(item).lower()})",
    ] + [f"trigger: {t}" for t in triggers]
    return {
        "type": "QUALITY_WITH_TRIGGER",
        "confidence": _confidence(item),
        "reason": reasons,
    }


# ----------------------------------------------------------------------
DETECTORS = (
    undervalued_quality,
    compounders,
    fundamental_acceleration,
    inflection_point,
    quality_with_trigger,
    turnarounds,
    special_situations,
)


def detect_opportunities(item: dict) -> list[dict]:
    """All opportunity types that match, strongest first."""
    return [detector(item) for detector in DETECTORS if detector(item) is not None]


def best_opportunity(item: dict) -> dict | None:
    """The most relevant opportunity, or None."""
    opportunities = detect_opportunities(item)
    return opportunities[0] if opportunities else None
