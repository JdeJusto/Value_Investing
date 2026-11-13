"""Guided prompts for the interactive menu.

The menu is a guided layer over the regular CLI: instead of asking the user
to type flags, every option asks for its inputs with numbered selectors,
numeric fields with visible defaults and yes/no questions.

All prompts respect ``--no-color`` / ``NO_COLOR`` through
:mod:`cli.theme`. ``q`` / ``back`` (or Ctrl+C / EOF) raises
:class:`PromptCancelled`, which the menu catches to return to the previous
screen without executing anything.
"""

from __future__ import annotations

from collections.abc import Callable

from cli import theme

_CANCEL_TOKENS = {"q", "back"}
_YES = {"y", "yes"}
_NO = {"n", "no"}


class PromptCancelled(Exception):
    """The user cancelled the current prompt (``q``, ``back`` or Ctrl+C)."""


# ---------------------------------------------------------------------------
# low-level input
# ---------------------------------------------------------------------------
def _read(prompt: str) -> str:
    """Read one line; Ctrl+C / EOF is a clean cancel, not a crash."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        raise PromptCancelled() from None


def _value(raw: str) -> str:
    value = raw.strip()
    if value.lower() in _CANCEL_TOKENS:
        raise PromptCancelled()
    return value


def _title(text: str) -> None:
    print(theme.color(text, theme.NEON_CYAN, theme.BOLD))


def _hint() -> None:
    print(theme.dim("  (q to cancel)"))


def _error(text: str) -> None:
    print(theme.neon_pink(f"  {text}"))


def _default_suffix(default) -> str:
    return theme.dim(f"[{default}]") if default is not None else ""


# ---------------------------------------------------------------------------
# selectors and fields
# ---------------------------------------------------------------------------
def ask_choice(
    title: str,
    options: list[tuple[str, str]],
    default_index: int = 0,
    *,
    allow_back: bool = True,
    aliases: dict[str, str] | None = None,
) -> str:
    """Show numbered options and return the selected value.

    ``aliases`` maps extra textual keys to values (e.g. ``{"c": "combine"}``
    for a ``[c] Combine`` option that also has a number).
    """
    if not options:
        raise ValueError("ask_choice needs at least one option")
    _title(title)
    for index, (label, _option_value) in enumerate(options, start=1):
        number = theme.color(f"[{index}]", theme.GOLD, theme.BOLD)
        print(f"  {number} {theme.neon_cyan(label)}")
    if allow_back:
        _hint()

    default_number = default_index + 1
    while True:
        raw = _value(_read(f"  Choice {_default_suffix(default_number)}: "))
        if not raw:
            return options[default_index][1]
        if aliases and raw.lower() in aliases:
            return aliases[raw.lower()]
        try:
            index = int(raw) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(options):
            return options[index][1]
        _error(f"Choose a number between 1 and {len(options)}.")


def ask_int(
    title: str,
    default: int | None = None,
    min_val: int | None = None,
    max_val: int | None = None,
) -> int:
    """Prompt for an integer with an optional range and visible default."""
    _title(title)
    _hint()
    while True:
        raw = _value(_read(f"  Value {_default_suffix(default)}: "))
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            _error(f"'{raw}' is not an integer.")
            continue
        if min_val is not None and value < min_val:
            _error(f"Must be >= {min_val}.")
            continue
        if max_val is not None and value > max_val:
            _error(f"Must be <= {max_val}.")
            continue
        return value


def ask_float(
    title: str,
    default: float | None = None,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    """Prompt for a float with an optional range and visible default."""
    _title(title)
    _hint()
    while True:
        raw = _value(_read(f"  Value {_default_suffix(default)}: "))
        if not raw and default is not None:
            return default
        try:
            value = float(raw)
        except ValueError:
            _error(f"'{raw}' is not a number.")
            continue
        if min_val is not None and value < min_val:
            _error(f"Must be >= {min_val:g}.")
            continue
        if max_val is not None and value > max_val:
            _error(f"Must be <= {max_val:g}.")
            continue
        return value


def ask_text(
    title: str,
    default: str | None = None,
    validator: Callable[[str], bool] | None = None,
    validator_error: str = "Invalid value",
    *,
    allow_empty: bool = False,
) -> str:
    """Prompt for text with an optional validator."""
    _title(title)
    _hint()
    while True:
        raw = _value(_read(f"  Value {_default_suffix(default)}: "))
        if not raw:
            if default is not None:
                value = default
            elif allow_empty:
                return ""
            else:
                _error("A value is required.")
                continue
        else:
            value = raw
        if validator is not None and not validator(value):
            _error(validator_error)
            continue
        return value


def ask_yes_no(title: str, default: bool = False) -> bool:
    """Prompt for y/n with the default shown as ``Y/n`` or ``y/N``."""
    _title(title)
    _hint()
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = _value(_read(f"  {suffix}: "))
        if not raw:
            return default
        lowered = raw.lower()
        if lowered in _YES:
            return True
        if lowered in _NO:
            return False
        _error("Enter y or n.")


# ---------------------------------------------------------------------------
# domain-specialized prompts
# ---------------------------------------------------------------------------
def ask_ticker(title: str = "Ticker", default: str | None = "AAPL") -> str:
    """Ask for a ticker and validate it against Financial-DataBase.

    A database outage degrades gracefully (the ticker is accepted) so the
    menu is not blocked by infrastructure trouble; an unknown ticker is
    re-prompted with a clear message.
    """
    from backend.services.ticker_resolver import resolve_ticker

    def _known(raw: str) -> bool:
        try:
            return resolve_ticker(raw) is not None
        except Exception:  # noqa: BLE001 — DB down: do not block the menu
            return True

    return ask_text(
        title,
        default=default,
        validator=_known,
        validator_error="Ticker not found in Financial-DataBase.",
    ).upper()


def ask_universe(default: str = "sp500") -> str:
    """Ask for a named universe (demo / indices / all)."""
    options = [
        ("demo (8 offline tickers)", "demo"),
        ("S&P 500", "sp500"),
        ("Nasdaq 100", "nasdaq100"),
        ("Russell 2000", "russell2000"),
        ("All", "all"),
    ]
    values = [value for _label, value in options]
    index = values.index(default) if default in values else 0
    return ask_choice("Universe", options, default_index=index)


def ask_strategy() -> str:
    """Ask for a combination strategy."""
    return ask_choice(
        "Strategy",
        [
            ("AND (all must pass)", "and"),
            ("OR (any can pass)", "or"),
            ("Weighted", "weighted"),
        ],
    )


def _methodology_names(names: list[str] | None) -> list[str]:
    from backend.methodologies.registry import discover, registry

    discover()
    return list(names) if names is not None else registry.list()


def _ask_multi(names: list[str], minimum: int = 2) -> list[str]:
    _title("Which methodologies? (comma-separated numbers)")
    for index, name in enumerate(names, start=1):
        number = theme.color(f"[{index}]", theme.GOLD, theme.BOLD)
        print(f"  {number} {theme.neon_cyan(name)}")
    _hint()
    while True:
        raw = _value(_read("  Selection (e.g. 1,7): "))
        if not raw:
            _error(f"Select at least {minimum}.")
            continue
        try:
            indexes = [int(part.strip()) - 1 for part in raw.split(",")]
        except ValueError:
            _error("Use numbers separated by commas.")
            continue
        if any(not (0 <= index < len(names)) for index in indexes):
            _error(f"Choose numbers between 1 and {len(names)}.")
            continue
        selected: list[str] = []
        for index in indexes:
            if names[index] not in selected:
                selected.append(names[index])
        if len(selected) < minimum:
            _error(f"Select at least {minimum} different methodologies.")
            continue
        return selected


def ask_methodology(
    title: str = "Which methodology?",
    *,
    include_combine: bool = False,
    combine_only: bool = False,
    names: list[str] | None = None,
) -> tuple[list[str], str | None]:
    """Select one methodology, or several plus a strategy.

    Returns ``(methodologies, strategy)``; ``strategy`` is ``None`` for a
    single-methodology flow. ``combine_only`` skips the single-select menu
    and goes straight to the multi-select + strategy prompts.
    """
    available = _methodology_names(names)
    if combine_only:
        return _ask_multi(available), ask_strategy()

    options = [(name, name) for name in available]
    aliases = None
    if include_combine:
        options.append(("[c] Combine multiple", "__combine__"))
        aliases = {"c": "__combine__", "combine": "__combine__"}
    selected = ask_choice(title, options, aliases=aliases)
    if selected != "__combine__":
        return [selected], None
    return _ask_multi(available), ask_strategy()
