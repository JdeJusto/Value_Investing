import math
from typing import Optional


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def green(text: str) -> str:
    return f"{Colors.GREEN}{text}{Colors.RESET}"


def red(text: str) -> str:
    return f"{Colors.RED}{text}{Colors.RESET}"


def yellow(text: str) -> str:
    return f"{Colors.YELLOW}{text}{Colors.RESET}"


def cyan(text: str) -> str:
    return f"{Colors.CYAN}{text}{Colors.RESET}"


def bold(text: str) -> str:
    return f"{Colors.BOLD}{text}{Colors.RESET}"


def dim(text: str) -> str:
    return f"{Colors.DIM}{text}{Colors.RESET}"


def fmt_pct(value: float | None, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return dim("N/A")
    return f"{value * 100:.{decimals}f}%"


def fmt_dollar(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return dim("N/A")
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"


def fmt_ratio(value: float | None, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return dim("N/A")
    return f"{value:.{decimals}f}"


def print_separator(char: str = "=", width: int = 72):
    print(char * width)


def print_header(text: str, char: str = "=", width: int = 72):
    print()
    print(char * width)
    print(f"  {text}")
    print(char * width)


def print_section(title: str):
    print()
    print(f"  {bold(title)}")
    print(f"  {dim('─' * 60)}")


def print_key_value(key: str, value: str, width: int = 28):
    print(f"  {key:>{width}} : {value}")


def print_table(
    headers: list[tuple[str, int]],
    rows: list[list[str]],
    title: str | None = None,
    padding: int = 2,
):
    if title:
        print()
        print(f"  {bold(title)}")
        print()

    col_widths = []
    for col_idx, (header, _) in enumerate(headers):
        max_w = len(header)
        for row in rows:
            if col_idx < len(row):
                max_w = max(max_w, len(remove_ansi(row[col_idx])))
        col_widths.append(max_w)

    header_parts = []
    sep_parts = []
    for col_idx, (header, align) in enumerate(headers):
        w = col_widths[col_idx]
        if align == 0:
            header_parts.append(header.ljust(w))
        else:
            header_parts.append(header.rjust(w))
        sep_parts.append("─" * w)

    header_line = "  " + "  ".join(bold(h) for h in header_parts)
    sep_line = "  " + "─".join(sep_parts)

    print(header_line)
    print(sep_line)

    for row in rows:
        parts = []
        for col_idx, (_, align) in enumerate(headers):
            w = col_widths[col_idx]
            val = row[col_idx] if col_idx < len(row) else ""
            if align == 0:
                parts.append(val.ljust(w + len(val) - len(remove_ansi(val))))
            else:
                parts.append(val.rjust(w + len(val) - len(remove_ansi(val))))
        print("  " + "  ".join(parts))

    print()


def remove_ansi(text: str) -> str:
    import re

    return re.sub(r"\033\[[0-9;]*m", "", text)
