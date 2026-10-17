"""Markdown export for the scorecard payload.

Pure string building: the input is ``Scorecard.to_dict()`` and the output is a
portable Markdown document (read it in any renderer, print it to PDF from
there, paste it into a report). No template engine, no HTML, no dependency —
and no I/O, so the same payload always yields byte-identical output.

The JSON export remains the machine contract (see the API's default
``format=json`` and the CLI's ``--json``); this is the human-facing one. The
exporter never computes a figure: every value it prints is already in the
payload it was handed.
"""

from __future__ import annotations

from typing import Any

#: Placeholder for a missing value. Never a fabricated 0.
DASH = "—"

#: Closing line, kept in one place so the three surfaces cannot diverge.
FOOTER = (
    "Data: Financial-DataBase · {period} data · Generated for informational "
    "purposes. Not investment advice."
)

#: Per-rule glyph, mirroring the CLI and the Streamlit table.
STATUS_MARK: dict[str, str] = {
    "PASS": "✓",
    "WATCH": "⚠",
    "FAIL": "✗",
    "INSUFFICIENT": "·",
}

#: Characters that change meaning inline; escaped with a backslash.
_INLINE_SPECIALS = frozenset("\\`*_[]<>|~")

#: Characters that would start a block if they led a line.
_BLOCK_LEADERS = frozenset("#>-+=")

#: The rule table's header, shared by the rows below it.
_RULE_HEADER = (
    "| Status | Rule | Value | Threshold | Why | Source | Peer median | Peer pct |",
    "|--------|------|-------|-----------|-----|--------|-------------|----------|",
)


def _text(value: Any) -> str:
    """Inline-safe Markdown for one user-controlled string.

    Collapses whitespace (so a table cannot break), escapes the characters
    that could change inline semantics, and neutralises a leading character
    that would start a block. Empty and ``None`` become the dash.
    """
    if value is None:
        return DASH
    collapsed = " ".join(str(value).split())
    if not collapsed:
        return DASH
    escaped = "".join(
        f"\\{char}" if char in _INLINE_SPECIALS else char for char in collapsed
    )
    if escaped[0] in _BLOCK_LEADERS:
        escaped = "\\" + escaped
    return escaped


def _cell(value: Any) -> str:
    """A table cell: :func:`_text` plus the pipe delimiter.

    ``|`` is already escaped by :func:`_text` (it is an inline special), so a
    label containing a pipe can never add a column.
    """
    return _text(value)


def _csv(value: Any) -> str:
    """One CSV field: quoted only when it would otherwise be ambiguous."""
    text = "" if value is None else " ".join(str(value).split())
    if any(char in text for char in ',"'):
        return '"' + text.replace('"', '""') + '"'
    return text


def _score_text(score: int | None) -> str:
    return DASH if score is None else f"{score}/10"


def _percent(value: float | None) -> str:
    return DASH if value is None else f"{round(float(value) * 100)}%"


def _title(card: dict[str, Any]) -> str:
    ticker = _text(card.get("ticker"))
    company = card.get("company")
    if company is None or not str(company).strip():
        return ticker
    return f"{ticker} — {_text(company)}"


def _peer_group_line(card: dict[str, Any]) -> str:
    """The resolved peer group, or how to produce one.

    Peers are additive, so the line is always present: absent data is
    explained instead of silently missing.
    """
    for dimension in card.get("dimensions") or []:
        group = dimension.get("peer_group")
        if not group:
            continue
        size = dimension.get("peer_group_size")
        level = dimension.get("peer_group_level") or "industry"
        size_text = f"{size} companies" if size else "size unknown"
        return f"**Peer group:** {_text(group)} ({_text(size_text)}, {_text(level)})"
    return "**Peer group:** not available (run scripts/build_peer_stats.py)"


def _summary_section(card: dict[str, Any]) -> list[str]:
    lines = [
        "## Summary",
        "",
        "| Dimension | Score | Verdict | Confidence | Evaluable rules |",
        "|-----------|------:|---------|------------|----------------:|",
    ]
    for dimension in card.get("dimensions") or []:
        lines.append(
            "| {label} | {score} | {verdict} | {confidence} | {rules} |".format(
                label=_cell(dimension.get("label")),
                score=_cell(_score_text(dimension.get("score"))),
                verdict=_cell(str(dimension.get("verdict") or "").upper()),
                confidence=_cell(dimension.get("confidence")),
                rules=_cell(dimension.get("evaluable_rules")),
            )
        )
    return lines


def _rule_row(rule: dict[str, Any]) -> str:
    status = STATUS_MARK.get(str(rule.get("status")), "·")
    cells = [
        status,
        _cell(rule.get("label")),
        _cell(rule.get("value")),
        _cell(rule.get("threshold")),
        _cell(rule.get("reason")),
        _cell(rule.get("source_methodology") or "analytics"),
        _cell(rule.get("peer_median")),
        _cell(_percent(rule.get("peer_percentile"))),
    ]
    return "| " + " | ".join(cells) + " |"


def _dimension_section(dimension: dict[str, Any]) -> list[str]:
    heading = "## {label} — {score} ({verdict}, {confidence})".format(
        label=_text(dimension.get("label")),
        score=_score_text(dimension.get("score")),
        verdict=_text(dimension.get("verdict")),
        confidence=_text(dimension.get("confidence")),
    )
    lines = [heading, ""]
    lines.extend(_RULE_HEADER)
    for rule in dimension.get("rules") or []:
        lines.append(_rule_row(rule))
    summary = dimension.get("summary")
    if summary:
        lines.extend(["", f"*{_text(summary)}*"])
    return lines


def _disagreements_section(card: dict[str, Any]) -> list[str]:
    lines = ["## Disagreements", ""]
    items = [item for item in (card.get("disagreements") or []) if str(item).strip()]
    if not items:
        lines.append("- None: the dimensions point in the same direction.")
        return lines
    lines.extend(f"- {_text(item)}" for item in items)
    return lines


def _charts_section(card: dict[str, Any]) -> list[str]:
    """The chart numbers as fenced CSV: no image, no renderer required."""
    lines = [
        "## Charts",
        "",
        (
            "Charts are rendered by the app and are not embedded here. The "
            "fenced CSV blocks below carry the same numbers for a renderer with "
            "a chart extension, or for a spreadsheet."
        ),
        "",
        "```csv",
        "dimension,score",
    ]
    for dimension in card.get("dimensions") or []:
        score = dimension.get("score")
        lines.append(f"{_csv(dimension.get('label'))},{_csv(_score_text(score))}")
    lines.extend(["```", "", "```csv", "dimension,status,rule,value"])
    for dimension in card.get("dimensions") or []:
        for rule in dimension.get("rules") or []:
            lines.append(
                ",".join(
                    [
                        _csv(dimension.get("label")),
                        _csv(rule.get("status")),
                        _csv(rule.get("label")),
                        _csv(rule.get("value")),
                    ]
                )
            )
    lines.append("```")
    return lines


def scorecard_to_markdown(
    scorecard: dict[str, Any],
    *,
    include_rules: bool = True,
    include_charts: bool = False,
) -> str:
    """Render a ``Scorecard.to_dict()`` payload as Markdown.

    ``include_rules=False`` emits only the summary table and the
    disagreements (a one-page brief); ``include_charts=True`` appends the
    chart data as fenced CSV blocks, since charts are never embedded.
    Deterministic: the same payload always produces the same string.
    """
    card = scorecard
    lines: list[str] = [f"# {_title(card)}", ""]
    lines.append(
        "**Sector:** {sector} · **Industry:** {industry}".format(
            sector=_text(card.get("sector")), industry=_text(card.get("industry"))
        )
    )
    lines.append("")
    lines.append(
        "**Overall:** {overall} · **Data quality:** {quality}".format(
            overall=_text(card.get("overall")),
            quality=_text(card.get("data_quality")),
        )
    )
    lines.append("")
    lines.append(_peer_group_line(card))
    lines.append("")
    lines.extend(_summary_section(card))

    if include_rules:
        for dimension in card.get("dimensions") or []:
            lines.append("")
            lines.extend(_dimension_section(dimension))

    lines.append("")
    lines.extend(_disagreements_section(card))

    if include_charts and include_rules:
        lines.append("")
        lines.extend(_charts_section(card))

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(FOOTER.format(period=_text(card.get("period"))))
    return "\n".join(lines) + "\n"
