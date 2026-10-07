import math

from backend.services import cli_output


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _colorize(code: str, text: str) -> str:
    """Wrap ``text`` in ``code`` only when colored output is enabled.

    Colors follow the shared rules (``--no-color``, ``NO_COLOR``, non-TTY
    stdout), so redirected output never contains escape codes.
    """
    if not cli_output.color_enabled():
        return text
    return f"{code}{text}{Colors.RESET}"


def green(text: str) -> str:
    return _colorize(Colors.GREEN, text)


def red(text: str) -> str:
    return _colorize(Colors.RED, text)


def yellow(text: str) -> str:
    return _colorize(Colors.YELLOW, text)


def cyan(text: str) -> str:
    return _colorize(Colors.CYAN, text)


def bold(text: str) -> str:
    return _colorize(Colors.BOLD, text)


def dim(text: str) -> str:
    return _colorize(Colors.DIM, text)


def verdict_color(verdict: str) -> str:
    """Method verdict -> terminal color (identity for HOLD/unknown)."""
    return {
        "BUY": green,
        "WATCH": yellow,
        "HOLD": lambda text: text,
        "AVOID": red,
        "N/A": dim,
        "INSUFFICIENT_DATA": dim,
    }.get(verdict, lambda text: text)(verdict)


def confidence_color(confidence: str) -> str:
    """Confidence level -> terminal color (identity for unknown)."""
    return {"HIGH": green, "MEDIUM": yellow, "LOW": red}.get(
        confidence, lambda text: text
    )(confidence)


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


def fmt_net_income(value: float | None, convention: str | None = None) -> str:
    """Net income with its accounting convention when it is not consolidated.

    "available_to_common" subtracts preferred dividends, so the figure is
    lower than the consolidated net income shown on EDGAR; the note keeps
    the difference from looking like a data error.
    """
    text = fmt_dollar(value) + " USD"
    if convention == "available_to_common":
        return text + dim(" (available to common; see README for convention)")
    return text


def fmt_ratio(value: float | None, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return dim("N/A")
    return f"{value:.{decimals}f}"


def print_separator(char: str = "=", width: int = 72):
    print(char * width)


def print_header(text: str, char: str = "=", width: int = 72):
    """Command banner, rendered as a bordered Rich panel.

    ``char`` and ``width`` only describe the old ``===`` rule; the panel sizes
    itself from the console, so they are accepted for signature compatibility.
    """
    cli_output.print_banner(text)


def print_section(title: str):
    """Section heading (bold title) followed by a dim rule."""
    console = cli_output.get_console()
    console.print()
    console.print(cli_output.heading(title), soft_wrap=True)
    console.print(cli_output.rule(), soft_wrap=True)


def print_key_value(key: str, value: str, width: int = 28):
    cli_output.get_console().print(
        cli_output.kv_line(key, value, width), soft_wrap=True
    )


def print_table(
    headers: list[tuple[str, int]],
    rows: list[list[str]],
    title: str | None = None,
    padding: int = 2,
):
    """Rich table: dim title, bold header, right-aligned columns (align 1)."""
    cli_output.get_console().print(
        cli_output.data_table(headers, rows, title=title, padding=padding)
    )


def remove_ansi(text: str) -> str:
    import re

    return re.sub(r"\033\[[0-9;]*m", "", text)


def valuation_table(ratios: list):
    """Historical valuation rows (P/E, FCF yield) as a Rich table.

    Same figures and formats as ``HistoricalValuationService``'s text
    rendering — ``.2f`` for price/EPS/P/E and ``.2%`` for the FCF yield,
    with ``N/A`` for missing values — rendered as right-aligned columns.
    """

    def _num(value, pattern: str = "{:.2f}") -> str:
        return pattern.format(value) if value is not None else "N/A"

    headers = [
        ("fiscal_year", 1),
        ("price", 1),
        ("eps", 1),
        ("pe_ratio", 1),
        ("fcf_yield", 1),
    ]
    rows = [
        [
            str(ratio.get("fiscal_year")),
            _num(ratio.get("price")),
            _num(ratio.get("eps")),
            _num(ratio.get("pe_ratio")),
            _num(ratio.get("fcf_yield"), "{:.2%}"),
        ]
        for ratio in ratios
    ]
    return cli_output.data_table(headers, rows)
