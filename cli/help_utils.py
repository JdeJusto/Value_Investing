"""Help utilities: search, suggestions and the grouped help footer."""

from __future__ import annotations

import difflib

from cli.command_catalog import (
    CATALOG,
    INTENT_ALIASES,
    CommandInfo,
    format_catalog,
    format_common_tasks,
)


def search_commands(query: str, limit: int = 5) -> list[CommandInfo]:
    """Rank catalog entries against a free-text query (substring, no fuzzy).

    Name matches beat keyword matches, which beat summary matches; ties break
    alphabetically so the output is deterministic.
    """
    terms = [term for term in str(query or "").lower().split() if term]
    if not terms:
        return []
    scored: list[tuple[int, CommandInfo]] = []
    for info in CATALOG.values():
        haystack_name = info.name.lower()
        keywords = tuple(keyword.lower() for keyword in info.keywords)
        summary = info.summary.lower()
        score = 0
        matched = False
        for term in terms:
            term_score = 0
            if term == haystack_name:
                term_score = 150
            elif haystack_name.startswith(term):
                term_score = 140
            elif term in haystack_name or (
                len(term) >= 8 and term[:8] in haystack_name
            ):
                term_score = 120
            elif term in keywords:
                term_score = 70
            elif any(term in keyword for keyword in keywords):
                term_score = 50
            elif term in summary:
                term_score = 25
            if term_score:
                matched = True
                score += term_score
        if matched:
            scored.append((score, info))
    scored.sort(key=lambda item: (-item[0], len(item[1].name), item[1].name))
    return [info for _score, info in scored[: max(1, int(limit))]]


def suggest_command(name: str) -> str | None:
    """Closest real command for a typo/intent, or None."""
    value = str(name or "").strip().lower()
    if not value:
        return None
    if value in INTENT_ALIASES:
        return INTENT_ALIASES[value]
    if value in CATALOG:
        return value
    close = difflib.get_close_matches(value, list(CATALOG), n=1, cutoff=0.6)
    return close[0] if close else None


def render_search_results(query: str, limit: int = 5) -> str:
    """Formatted top matches (empty string when nothing matches)."""
    matches = search_commands(query, limit=limit)
    if not matches:
        return ""
    lines = [f"Top matches for '{query}':", ""]
    for info in matches:
        lines.append(f"  vi {info.name}  [{info.category}]")
        lines.append(f"    {info.summary}")
        lines.append(f"    Example: {info.example}")
        lines.append("")
    lines.append("Run 'vi help <command>' for the full flags.")
    return "\n".join(lines)


def render_help_footer() -> str:
    """Common tasks + the categorized command list for ``vi --help``."""
    return f"{format_common_tasks()}\n\n{format_catalog()}\n\nSearch: vi help --search <query>"
