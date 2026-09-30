import math


def interpret_roe(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.15:
        return "Bueno (>15%)"
    if val > 0.08:
        return "Aceptable (8-15%)"
    return "Malo (<8%)"


def interpret_pb(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val < 1.0:
        return "Muy barato (<1)"
    if val < 1.5:
        return "Bueno (<1.5)"
    if val < 3.0:
        return "Normal (1.5-3)"
    return "Caro (>3)"


def interpret_fcf_yield(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.06:
        return "Bueno (>6%)"
    if val > 0.03:
        return "Aceptable (3-6%)"
    return "Bajo (<3%)"


def interpret_op_margin(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.20:
        return "Excelente (>20%)"
    if val > 0.10:
        return "Normal (10-20%)"
    return "Bajo (<10%)"


def interpret_net_margin(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.15:
        return "Bueno (>15%)"
    if val > 0.05:
        return "Aceptable (5-15%)"
    return "Bajo (<5%)"


def interpret_roic(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.12:
        return "Bueno (>12%)"
    if val > 0.06:
        return "Normal (6-12%)"
    return "Malo (<6%)"


def interpret_inc_roic(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.10:
        return "Creando valor (>10%)"
    if val > 0:
        return "Positivo pero bajo"
    return "Destruyendo valor"


def interpret_ev_ebit(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val < 10:
        return "Barato (<10x)"
    if val < 18:
        return "Razonable (10-18x)"
    return "Caro (>18x)"


def interpret_owner_earnings(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    return f"{val:,.0f} USD"


def interpret_piotroski(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val >= 8:
        return "Muy fuerte (8-9)"
    if val >= 5:
        return "Normal (5-7)"
    return "Debil (<5)"


def interpret_altman_z(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 2.99:
        return "Zona segura"
    if val > 1.8:
        return "Zona gris"
    return "Riesgo de quiebra"


def interpret_net_debt_ebitda(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val < 1:
        return "Muy bajo riesgo"
    if val < 3:
        return "Aceptable (1-3)"
    return "Endeudado (>3)"


def interpret_interest_coverage(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 5:
        return "Seguro (>5x)"
    if val > 2:
        return "Riesgo moderado (2-5x)"
    return "Alto riesgo (<2x)"


def interpret_gm_stability(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val < 0.03:
        return "Muy estable (<3%)"
    if val < 0.08:
        return "Algo variable (3-8%)"
    return "Volatil (>8%)"


def interpret_fcf_conversion(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.8:
        return "Excelente (>80%)"
    if val > 0.5:
        return "Normal (50-80%)"
    return "Debil (<50%)"


def interpret_croic(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.10:
        return "Bueno (>10%)"
    if val > 0.04:
        return "Aceptable (4-10%)"
    return "Bajo (<4%)"


def interpret_acquirers_multiple(val):
    return interpret_ev_ebit(val)


def interpret_dcf_value(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    return f"{val:,.0f} USD"


def interpret_shareholder_yield(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "Sin datos"
    if val > 0.04:
        return "Alto (>4%)"
    if val > 0.02:
        return "Moderado (2-4%)"
    return "Bajo (<2%)"


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
