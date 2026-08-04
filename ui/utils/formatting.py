def fmt_usd(val: float | None) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"${val / 1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"${val / 1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val / 1e6:.2f}M"
    return f"${val:,.2f}"


def fmt_pct(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.{decimals}f}%"


def fmt_ratio(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}"


def fmt_num(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.{decimals}f}"
