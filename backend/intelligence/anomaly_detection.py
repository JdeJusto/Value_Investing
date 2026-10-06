"""Anomaly detection over normalized fundamentals.

Flags the latest year when a metric lies far outside its own historical
distribution (z-score vs the mean/std of the years *before* it) or
jumps abnormally year over year. Deterministic, no ML, no providers.
"""

from collections.abc import Callable

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.intelligence.quality_metrics import gross_margin, ordered_asc, roic

ANOMALY_ZSCORE = 2.0
SEVERE_ZSCORE = 3.0
ABNORMAL_YOY_CHANGE = 0.50
MIN_HISTORY = 3  # baseline years required for a z-score


def _stats(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, variance**0.5


def _series(rows: list[NormalizedFinancials], getter: Callable) -> list[float]:
    return [v for r in rows if (v := getter(r)) is not None]


def _zscore_anomaly(
    metric: str,
    rows: list[NormalizedFinancials],
    getter: Callable,
    threshold: float,
) -> dict | None:
    if len(rows) < MIN_HISTORY + 1:
        return None
    ordered = ordered_asc(rows)
    baseline = _series(ordered[:-1], getter)
    if len(baseline) < MIN_HISTORY:
        return None
    value = getter(ordered[-1])
    if value is None:
        return None
    mean, stddev = _stats(baseline)
    if stddev == 0:
        return None
    zscore = (value - mean) / stddev
    if abs(zscore) < threshold:
        return None
    return {
        "type": "zscore",
        "metric": metric,
        "year": ordered[-1].fiscal_year,
        "value": round(value, 6),
        "mean": round(mean, 6),
        "stddev": round(stddev, 6),
        "zscore": round(zscore, 2),
        "direction": "UP" if zscore > 0 else "DOWN",
        "severity": "STRONG" if abs(zscore) >= SEVERE_ZSCORE else "MILD",
    }


def _yoy_anomaly(
    metric: str,
    rows: list[NormalizedFinancials],
    getter: Callable,
    change_threshold: float,
) -> dict | None:
    ordered = ordered_asc(rows)
    if len(ordered) < 2:
        return None
    prev = getter(ordered[-2])
    last = getter(ordered[-1])
    if prev is None or last is None or prev == 0:
        return None
    change = (last - prev) / abs(prev)
    if abs(change) < change_threshold:
        return None
    return {
        "type": "yoy_jump",
        "metric": metric,
        "year": ordered[-1].fiscal_year,
        "value": round(last, 6),
        "change": round(change, 4),
        "direction": "UP" if change > 0 else "DOWN",
        "severity": "STRONG" if abs(change) >= 1.0 else "MILD",
    }


_ZSCORE_METRICS: tuple[tuple[str, Callable], ...] = (
    ("revenue", lambda r: r.revenue),
    ("net_income", lambda r: r.net_income),
    ("gross_margin", gross_margin),
    ("free_cash_flow", lambda r: r.free_cash_flow),
    ("roic", roic),
)

_YOY_METRICS: tuple[tuple[str, Callable], ...] = (
    ("revenue", lambda r: r.revenue),
    ("net_income", lambda r: r.net_income),
    ("free_cash_flow", lambda r: r.free_cash_flow),
)


def detect_anomalies(
    rows: list[NormalizedFinancials],
    zscore_threshold: float = ANOMALY_ZSCORE,
    yoy_threshold: float = ABNORMAL_YOY_CHANGE,
) -> list[dict]:
    """Flag the latest year against its own history.

    Anomalies are ordered by strength (z-score first, then jumps),
    and every entry carries a human-readable explanation.
    """
    anomalies: list[dict] = []
    for metric, getter in _ZSCORE_METRICS:
        anomaly = _zscore_anomaly(metric, rows, getter, zscore_threshold)
        if anomaly:
            anomalies.append(anomaly)
    for metric, getter in _YOY_METRICS:
        anomaly = _yoy_anomaly(metric, rows, getter, yoy_threshold)
        if anomaly:
            anomalies.append(anomaly)

    def strength(a: dict) -> float:
        if a["type"] == "zscore":
            return abs(a["zscore"])
        return abs(a["change"]) * 2.0

    return sorted(anomalies, key=strength, reverse=True)


def anomaly_summary(anomalies: list[dict]) -> str:
    """One-line summary for reporting: number and strongest anomaly."""
    if not anomalies:
        return "no anomalies in the latest fiscal year"
    strongest = anomalies[0]
    count = len(anomalies)
    label = "anomaly" if count == 1 else "anomalies"
    return (
        f"{count} {label}; strongest: {strongest['metric']} "
        f"{strongest['direction'].lower()} (z={strongest.get('zscore', 'n/a')})"
    )
