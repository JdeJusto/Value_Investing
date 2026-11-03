"""The Markdown exporter: shape, escaping, determinism and the two switches.

The exporter is a pure function of the ``to_dict()`` payload, so these tests
feed it a crafted payload — no database, no prices, no scorecard computation.
"""

from __future__ import annotations

import pytest

from backend.services.scorecard_export import (
    DASH,
    FOOTER,
    STATUS_MARK,
    scorecard_to_markdown,
)

_DIMENSIONS = (
    ("growth", "Growth"),
    ("profitability", "Profitability"),
    ("financial_health", "Financial Health"),
    ("valuation", "Valuation"),
    ("shareholder_returns", "Shareholder Returns"),
    ("management_moat", "Management/Moat"),
)


def _rule(key: str, *, peers: bool = False, value: str | None = "12.4%") -> dict:
    return {
        "rule_id": f"{key}_rule",
        "label": f"{key} rule",
        "status": "PASS",
        "value": value,
        "threshold": "≥ 10%",
        "reason": "clears the bar",
        "source_metric": "revenue_cagr_5y",
        "source_methodology": "graham" if key == "valuation" else None,
        "source_book": None,
        "peer_median": "15.50x" if peers else None,
        "peer_percentile": 0.62 if peers else None,
    }


def _payload(*, company: str = "Apple Inc.", peers: bool = False) -> dict:
    return {
        "ticker": "AAPL",
        "company": company,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "period": "FY",
        "price": 240.0,
        "market_cap": 3.6e12,
        "generated": "2026-10-17T00:00:00Z",
        "dimensions": [
            {
                "key": key,
                "label": label,
                "question": "q",
                "score": 7,
                "verdict": "Mixed",
                "confidence": "HIGH",
                "evaluable_rules": 4,
                "rules": [_rule(key, peers=peers)],
                "trend": "stable",
                "summary": f"{key} summary",
                "peer_group": "Technology" if peers else None,
                "peer_group_level": "sector" if peers else None,
                "peer_group_size": 89 if peers else None,
            }
            for key, label in _DIMENSIONS
        ],
        "overall": "Mixed",
        "disagreements": ["Valuation is weak (2/10) while Growth is strong (growth)."],
        "methodologies": [],
        "data_quality": "HIGH",
        "notes": [],
    }


def _cells(row: str) -> list[str]:
    """Split one table row on its unescaped pipes (drops the escape marks)."""
    out: list[str] = []
    current: list[str] = []
    escaped = False
    for char in row.strip().strip("|"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            out.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    out.append("".join(current).strip())
    return out


def _sections(markdown: str) -> dict[str, str]:
    """Map each ``## Heading`` to the block that follows it."""
    blocks: dict[str, str] = {}
    heading: str | None = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            heading = line[3:]
            blocks[heading] = ""
        elif heading is not None:
            blocks[heading] += line + "\n"
    return blocks


def _tables(markdown: str) -> list[list[str]]:
    """Every Markdown table as a list of cell-lists (rows keep their order)."""
    tables: list[list[str]] = []
    current: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("|"):
            current.append(line)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


# ---------------------------------------------------------------------------
# shape
# ---------------------------------------------------------------------------
def test_header_carries_identity_sector_quality_and_peer_group():
    markdown = scorecard_to_markdown(_payload(peers=True))
    assert markdown.startswith("# AAPL — Apple Inc.\n")
    assert "**Sector:** Technology · **Industry:** Consumer Electronics" in markdown
    assert "**Overall:** Mixed · **Data quality:** HIGH" in markdown
    assert "**Peer group:** Technology (89 companies, sector)" in markdown


def test_peer_group_line_explains_a_missing_artifact():
    markdown = scorecard_to_markdown(_payload())
    assert "**Peer group:** not available (run scripts/build_peer_stats.py)" in markdown


def test_summary_lists_every_dimension_with_its_score_and_verdict():
    blocks = _sections(scorecard_to_markdown(_payload()))
    rows = blocks["Summary"].strip().splitlines()
    header, _, *body = rows
    assert _cells(header) == [
        "Dimension",
        "Score",
        "Verdict",
        "Confidence",
        "Evaluable rules",
    ]
    assert len(body) == len(_DIMENSIONS)
    for row, (_, label) in zip(body, _DIMENSIONS):
        assert _cells(row) == [label, "7/10", "MIXED", "HIGH", "4"]


def test_each_dimension_gets_a_section_with_a_eight_column_rule_table():
    markdown = scorecard_to_markdown(_payload())
    blocks = _sections(markdown)
    for key, label in _DIMENSIONS:
        heading = next(name for name in blocks if name.startswith(f"{label} — "))
        assert heading == f"{label} — 7/10 (Mixed, HIGH)"
        rows = [line for line in blocks[heading].splitlines() if line.startswith("|")]
        header, divider, *body = rows
        assert _cells(header) == [
            "Status",
            "Rule",
            "Value",
            "Threshold",
            "Why",
            "Source",
            "Peer median",
            "Peer pct",
        ]
        assert len(body) == 1
        assert _cells(body[0]) == [
            STATUS_MARK["PASS"],
            f"{key} rule",
            "12.4%",
            "≥ 10%",
            "clears the bar",
            "graham" if key == "valuation" else "analytics",
            DASH,
            DASH,
        ]
        assert divider.startswith("|---")


def test_peer_columns_carry_the_median_and_a_rounded_percentile():
    markdown = scorecard_to_markdown(_payload(peers=True))
    assert (
        "| ✓ | growth rule | 12.4% | ≥ 10% | clears the bar | analytics | 15.50x | 62% |"
        in markdown
    )


def test_disagreements_are_bulleted():
    blocks = _sections(scorecard_to_markdown(_payload()))
    items = [
        line for line in blocks["Disagreements"].splitlines() if line.startswith("- ")
    ]
    assert items == ["- Valuation is weak (2/10) while Growth is strong (growth)."]


def test_no_disagreements_says_so_instead_of_leaving_a_blank_section():
    payload = _payload()
    payload["disagreements"] = []
    blocks = _sections(scorecard_to_markdown(payload))
    assert blocks["Disagreements"].strip().splitlines()[0] == (
        "- None: the dimensions point in the same direction."
    )


def test_footer_uses_the_period_and_the_advice_disclaimer():
    markdown = scorecard_to_markdown(_payload())
    assert markdown.rstrip().endswith(FOOTER.format(period="FY"))
    assert "\n---\n" in markdown
    assert "Not investment advice." in markdown


# ---------------------------------------------------------------------------
# missing data
# ---------------------------------------------------------------------------
def test_none_score_and_missing_strings_become_the_dash():
    payload = _payload()
    payload["sector"] = None
    payload["dimensions"][0]["score"] = None
    payload["dimensions"][0]["verdict"] = "Insufficient"
    payload["dimensions"][0]["rules"] = []
    markdown = scorecard_to_markdown(payload)
    assert "**Sector:** " + DASH + " · **Industry:** Consumer Electronics" in markdown
    assert f"| Growth | {DASH} | INSUFFICIENT | HIGH | 4 |" in markdown
    assert "## Growth — " + DASH + " (Insufficient, HIGH)" in markdown


def test_a_company_without_a_name_still_has_a_heading():
    payload = _payload(company=None)
    assert scorecard_to_markdown(payload).startswith("# AAPL\n")


# ---------------------------------------------------------------------------
# escaping
# ---------------------------------------------------------------------------
def test_pipes_in_user_strings_can_never_add_a_column():
    payload = _payload(company="A | B")
    payload["dimensions"][0]["rules"][0]["reason"] = "left | right"
    markdown = scorecard_to_markdown(payload)
    assert "# AAPL — A \\| B" in markdown
    assert "left \\| right" in markdown
    # Every table keeps a rectangular shape despite the injected pipes.
    for table in _tables(markdown):
        widths = {len(_cells(row)) for row in table}
        assert len(widths) == 1
    # The literal, unescaped strings never appear.
    assert "A | B" not in markdown
    assert "left | right" not in markdown


def test_emphasis_and_leading_block_markers_are_escaped():
    markdown = scorecard_to_markdown(_payload(company="*Acme* — [x]"))
    assert "# AAPL — \\*Acme\\* — \\[x\\]" in markdown


def test_a_rule_label_that_starts_a_list_is_escaped():
    payload = _payload()
    payload["dimensions"][0]["rules"][0]["label"] = "- not a bullet"
    markdown = scorecard_to_markdown(payload)
    assert "\\- not a bullet" in markdown


def test_newlines_in_a_cell_are_collapsed():
    payload = _payload()
    payload["dimensions"][0]["rules"][0]["reason"] = "two\nlines"
    assert "two lines" in scorecard_to_markdown(payload)


# ---------------------------------------------------------------------------
# switches and determinism
# ---------------------------------------------------------------------------
def test_without_rules_only_the_summary_and_the_disagreements_remain():
    markdown = scorecard_to_markdown(_payload(), include_rules=False)
    blocks = _sections(markdown)
    assert set(blocks) == {"Summary", "Disagreements"}
    assert "## Growth" not in markdown
    assert "| Status |" not in markdown


def test_charts_are_not_embedded_by_default():
    markdown = scorecard_to_markdown(_payload())
    assert "## Charts" not in markdown
    assert "```" not in markdown


def test_charts_emit_fenced_csv_blocks_when_asked():
    markdown = scorecard_to_markdown(_payload(), include_charts=True)
    blocks = _sections(markdown)
    charts = blocks["Charts"]
    assert charts.count("```csv") == 2
    assert "dimension,score" in charts
    assert "dimension,status,rule,value" in charts
    assert "Growth,7/10" in charts
    assert "Growth,PASS,growth rule,12.4%" in charts


def test_charts_follow_the_rules_switch():
    markdown = scorecard_to_markdown(
        _payload(), include_rules=False, include_charts=True
    )
    assert "## Charts" not in markdown


def test_a_comma_in_a_value_is_quoted_in_the_charts_csv():
    payload = _payload()
    payload["dimensions"][0]["rules"][0]["label"] = "Revenue, net"
    markdown = scorecard_to_markdown(payload, include_charts=True)
    assert '"Revenue, net"' in markdown


@pytest.mark.parametrize(
    "kwargs", [{}, {"include_rules": False}, {"include_charts": True}]
)
def test_output_is_byte_identical_on_every_call(kwargs):
    first = scorecard_to_markdown(_payload(peers=True), **kwargs)
    second = scorecard_to_markdown(_payload(peers=True), **kwargs)
    assert first == second
    assert first.endswith("\n")
    assert not first.endswith("\n\n")
