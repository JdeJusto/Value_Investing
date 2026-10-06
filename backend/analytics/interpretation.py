import math


def interpret_roe(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.15:
        return "Good (>15%)"
    if val > 0.08:
        return "Acceptable (8-15%)"
    return "Poor (<8%)"


def interpret_pb(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val < 1.0:
        return "Very cheap (<1)"
    if val < 1.5:
        return "Good (<1.5)"
    if val < 3.0:
        return "Normal (1.5-3)"
    return "Expensive (>3)"


def interpret_fcf_yield(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.06:
        return "Good (>6%)"
    if val > 0.03:
        return "Acceptable (3-6%)"
    return "Low (<3%)"


def interpret_op_margin(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.20:
        return "Excellent (>20%)"
    if val > 0.10:
        return "Normal (10-20%)"
    return "Low (<10%)"


def interpret_net_margin(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.15:
        return "Good (>15%)"
    if val > 0.05:
        return "Acceptable (5-15%)"
    return "Low (<5%)"


def interpret_roic(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.12:
        return "Good (>12%)"
    if val > 0.06:
        return "Normal (6-12%)"
    return "Poor (<6%)"


def interpret_inc_roic(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.10:
        return "Creating value (>10%)"
    if val > 0:
        return "Positive but low"
    return "Destroying value"


def interpret_ev_ebit(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val < 10:
        return "Cheap (<10x)"
    if val < 18:
        return "Reasonable (10-18x)"
    return "Expensive (>18x)"


def interpret_owner_earnings(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    return f"{val:,.0f} USD"


def interpret_piotroski(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val >= 8:
        return "Very strong (8-9)"
    if val >= 5:
        return "Normal (5-7)"
    return "Weak (<5)"


def interpret_altman_z(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 2.99:
        return "Safe zone"
    if val > 1.8:
        return "Grey zone"
    return "Bankruptcy risk"


def interpret_net_debt_ebitda(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val < 1:
        return "Very low risk"
    if val < 3:
        return "Acceptable (1-3)"
    return "Leveraged (>3)"


def interpret_interest_coverage(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 5:
        return "Safe (>5x)"
    if val > 2:
        return "Moderate risk (2-5x)"
    return "High risk (<2x)"


def interpret_gm_stability(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val < 0.03:
        return "Very stable (<3%)"
    if val < 0.08:
        return "Somewhat variable (3-8%)"
    return "Volatile (>8%)"


def interpret_fcf_conversion(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.8:
        return "Excellent (>80%)"
    if val > 0.5:
        return "Normal (50-80%)"
    return "Weak (<50%)"


def interpret_croic(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.10:
        return "Good (>10%)"
    if val > 0.04:
        return "Acceptable (4-10%)"
    return "Low (<4%)"


def interpret_acquirers_multiple(val):
    return interpret_ev_ebit(val)


def interpret_dcf_value(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    return f"{val:,.0f} USD"


def interpret_shareholder_yield(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "No data"
    if val > 0.04:
        return "High (>4%)"
    if val > 0.02:
        return "Moderate (2-4%)"
    return "Low (<2%)"


INTERPRETERS = {
    "roe": interpret_roe,
    "pb": interpret_pb,
    "fcf_yield": interpret_fcf_yield,
    "operating_margin": interpret_op_margin,
    "net_margin": interpret_net_margin,
    "roic": interpret_roic,
    "incremental_roic": interpret_inc_roic,
    "ev_ebit": interpret_ev_ebit,
    "owner_earnings": interpret_owner_earnings,
    "piotroski_fscore": interpret_piotroski,
    "altman_zscore": interpret_altman_z,
    "net_debt_to_ebitda": interpret_net_debt_ebitda,
    "interest_coverage": interpret_interest_coverage,
    "gross_margin_stability": interpret_gm_stability,
    "fcf_conversion": interpret_fcf_conversion,
    "croic": interpret_croic,
    "acquirers_multiple": interpret_acquirers_multiple,
    "dcf_value": interpret_dcf_value,
    "shareholder_yield": interpret_shareholder_yield,
}

METRICS_ORDER = [
    "roe",
    "pb",
    "fcf_yield",
    "operating_margin",
    "net_margin",
    "roic",
    "incremental_roic",
    "ev_ebit",
    "owner_earnings",
    "piotroski_fscore",
    "altman_zscore",
    "net_debt_to_ebitda",
    "interest_coverage",
    "gross_margin_stability",
    "fcf_conversion",
    "croic",
    "acquirers_multiple",
    "dcf_value",
    "shareholder_yield",
]


def format_metric_value(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    if isinstance(val, float):
        if abs(val) > 1e6:
            return f"{val:,.0f}"
        elif abs(val) < 0.0001 and val != 0:
            return f"{val:.6f}"
        else:
            return f"{val:.4f}"
    return str(val)


def print_analysis(result):
    ticker = result.get("ticker", "?")
    score = result.get("score", None)
    print(f"\n{'=' * 60}")
    label = f"{ticker} - Score: {score:.4f}" if score else f"{ticker} - Sin score"
    print(f"{ticker} {label}")
    print("=" * 60)

    for metric in METRICS_ORDER:
        val = result.get(metric)
        form_val = format_metric_value(val)
        interpret_func = INTERPRETERS.get(metric)
        interpretation = interpret_func(val) if interpret_func else ""
        print(f"{metric:>25} : {form_val:<12} {interpretation}")

    print(f"\n{' Informacion adicional ':-^60}")
    for extra in ["market_cap", "revenue", "net_income", "fcf"]:
        if extra in result and result[extra] is not None:
            val = result[extra]
            print(f"{extra:>25} : {format_metric_value(val)} USD")
    print("=" * 60)
