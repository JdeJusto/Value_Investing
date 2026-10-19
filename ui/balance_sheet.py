"""Classic T-format balance sheet (Assets | Liabilities + Equity) for the Financials tab.

Pure model (``build_balance_model``) + Streamlit renderer
(``render_balance_sheet``). The model consumes a *numeric* fact matrix —
``{concept: {fiscal_year: float}}`` — which the page builds either from the
raw repository facts (live mode: exact) or by deterministically parsing the
abbreviated display strings of the demo fixtures (demo mode: 2-decimal
precision, so the balance check carries a rounding tolerance).

Subtotals are painted as reported when the filing states them
(``AssetsCurrent``, ``Liabilities``, ``StockholdersEquity``…) and computed
explicitly otherwise; the UI never invents a subtotal silently — computed
ones are labelled as such (``*``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape

import streamlit as st

from backend.services.ui_format import abbreviate_number
from ui.balance_map import (
    BALANCE_MAP,
    CONTRA_CONCEPTS,
    MASS_COLUMN,
    MASS_ORDER,
    MASS_SUBTOTAL_CONCEPTS,
    TOTAL_CONCEPTS,
    concept_mass,
    is_memorandum,
    mass_labels,
)
from ui.theme.format import (
    DASH,
    fmt_delta,
    fmt_money,
    fmt_pct,
    is_monetary,
)
from ui.theme.labels import label as human_label

#: Balance tolerance: exact for raw filings, rounding-aware for the demo
#: fixtures whose values are pre-abbreviated to 2 decimals ("$35.93B").
BALANCE_TOLERANCE_RATIO = 0.01
BALANCE_TOLERANCE_MIN = 1.0

#: Display scales offered by the unit selector (label -> scale key).
SCALE_CHOICES = {
    "As reported": "raw",
    "thousands (k)": "k",
    "millions (M)": "M",
    "billions (B)": "B",
}

_SUFFIX_FACTORS = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
_NUMBER = re.compile(r"\(?\$?\s*(-?[\d,.]+)\s*([TBMK])?(?:\s*sh)?\s*\)?")


def parse_display_value(text: object, unit: str = "") -> float | None:
    """Parse a backend display string back to a number.

    Handles the statement convention used by the Financials view and the
    demo fixtures: ``"$35.93B"`` -> ``35.93e9``, ``"($1.24M)"`` -> ``-1.24e6``,
    ``"14.77B sh"`` -> ``14.77e9``, ``"12,345"`` -> ``12345``, ``""``/``"—"``
    -> ``None``. ``unit="pure"`` disables K/M/B/T scaling.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw == DASH:
        return None
    match = _NUMBER.search(raw)
    if not match:
        return None
    negative = raw.startswith("(")
    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    factor = 1.0 if unit == "pure" else _SUFFIX_FACTORS.get(match.group(2) or "", 1.0)
    value = amount * factor
    return -value if negative else value


def numeric_from_facts(
    facts: list[dict],
    years: list[int],
) -> tuple[dict[str, dict[int, float]], dict[str, str]]:
    """Numeric matrix from raw repository facts (live mode, exact values).

    Uses the backend's ``dedupe_facts`` (read-only) so the T view resolves
    the same fact per (concept, year) as the flat tables.
    """
    from backend.services.financials_view_service import dedupe_facts

    latest = dedupe_facts(facts, set(years))
    numeric: dict[str, dict[int, float]] = {}
    units: dict[str, str] = {}
    for (concept, year), fact in latest.items():
        value = fact.get("value")
        if value is None:
            continue
        try:
            numeric.setdefault(concept, {})[year] = float(value)
        except (TypeError, ValueError):
            continue
        units.setdefault(concept, str(fact.get("unit") or ""))
    return numeric, units


def numeric_from_view(view: object) -> tuple[dict[str, dict[int, float]], dict[str, str]]:
    """Numeric matrix by parsing the view's display strings (demo mode).

    Deterministic (the backend format is), but only as precise as the
    abbreviated strings — hence the rounding tolerance in the model.
    """
    numeric: dict[str, dict[int, float]] = {}
    units: dict[str, str] = {}
    rows = list(view.balance_sheet) + list(getattr(view, "other", []))
    for row in rows:
        units.setdefault(row.concept, row.unit)
        for year, text in row.values.items():
            value = parse_display_value(text, row.unit)
            if value is not None:
                numeric.setdefault(row.concept, {})[int(year)] = value
    return numeric, units


@dataclass(frozen=True)
class BalanceLine:
    """One line item: the winning concept of a slot and its value (None = missing)."""

    concept: str
    label: str
    value: float | None
    prev_value: float | None = None


@dataclass(frozen=True)
class BalanceMass:
    """One balance-sheet mass with its lines and resolved subtotal."""

    key: str
    label: str
    lines: list[BalanceLine]
    subtotal: float | None
    subtotal_reported: bool


@dataclass(frozen=True)
class BalanceModel:
    """The whole T: five masses, unmapped leftovers and the totals."""

    year: int
    currency: str
    masses: list[BalanceMass]
    other_assets: list[BalanceLine] = field(default_factory=list)
    other_liabilities: list[BalanceLine] = field(default_factory=list)
    total_assets: float | None = None
    total_assets_reported: bool = False
    total_liabilities: float | None = None
    total_liabilities_reported: bool = False
    total_equity: float | None = None
    total_equity_reported: bool = False
    delta: float | None = None
    balanced: bool | None = None  # None = cannot evaluate (totals missing)
    partial: bool = False
    memoranda: list[BalanceLine] = field(default_factory=list)


def _first_present(
    concepts: list[str], numeric: dict[str, dict[int, float]], year: int
) -> tuple[str, float] | None:
    for concept in concepts:
        value = numeric.get(concept, {}).get(year)
        if value is not None:
            return concept, value
    return None


def _slot_line(
    slot: list[str],
    numeric: dict[str, dict[int, float]],
    year: int,
    prev_year: int | None,
) -> BalanceLine | None:
    """Resolve one alias-slot to its line (any-year presence keeps it visible).

    Contra concepts (``CONTRA_CONCEPTS``) are reported as positive numbers
    and are flipped here so the line renders and sums as a negative.
    """
    for concept in slot:
        years_values = numeric.get(concept)
        if not years_values:
            continue
        sign = -1.0 if concept in CONTRA_CONCEPTS else 1.0
        value = years_values.get(year)
        prev_value = years_values.get(prev_year) if prev_year else None
        return BalanceLine(
            concept=concept,
            label=human_label(concept),
            value=sign * value if value is not None else None,
            prev_value=sign * prev_value if prev_value is not None else None,
        )
    return None


def _resolve_mass(
    mass: str,
    numeric: dict[str, dict[int, float]],
    year: int,
    prev_year: int | None,
) -> tuple[BalanceMass, bool]:
    """Lines + subtotal of one mass; returns (mass, partial_flag)."""
    lines: list[BalanceLine] = []
    partial = False
    for slot in BALANCE_MAP[mass]:
        line = _slot_line(slot, numeric, year, prev_year)
        if line is None:
            continue
        if line.value is None:
            partial = True
        lines.append(line)
    reported = _first_present(MASS_SUBTOTAL_CONCEPTS.get(mass, []), numeric, year)
    if reported is not None:
        subtotal, reported_flag = reported[1], True
    elif any(line.value is not None for line in lines):
        subtotal = sum(line.value for line in lines if line.value is not None)
        reported_flag = False
    else:
        subtotal, reported_flag = None, False
    return (
        BalanceMass(
            key=mass,
            label=mass_labels(mass),
            lines=lines,
            subtotal=subtotal,
            subtotal_reported=reported_flag,
        ),
        partial,
    )


def _unmapped_column(concept: str) -> str:
    """Which T column an unmapped monetary concept belongs to.

    Liability-side keywords first, then the equity-side family (capital,
    stock, retained earnings, minority interest…) so leftovers never land
    in the Assets column by accident. The rest defaults to Assets.
    """
    lowered = concept.lower()
    liability_terms = (
        "liabilit",
        "payable",
        "equity",
        "capital",
        "stock",
        "preferred",
        "treasury",
        "retained",
        "earnings",
        "deficit",
        "comprehensive",
        "minority",
    )
    if any(term in lowered for term in liability_terms):
        return "liabilities"
    return "assets"


def build_balance_model(
    numeric: dict[str, dict[int, float]],
    units: dict[str, str],
    year: int,
    years: list[int] | None = None,
) -> BalanceModel:
    """Build the T model for ``year`` from the numeric fact matrix.

    Subtotals: painted from the filing when reported, otherwise computed as
    the sum of the present lines (``subtotal_reported=False``). Totals
    follow the same rule; ``balanced`` is ``None`` until all three totals
    exist. A line missing for this year but present in another year renders
    as a dash and flags the model as partial.
    """
    known_years = sorted({y for values in numeric.values() for y in values})
    prev_candidates = [y for y in known_years if y < year]
    prev_year = max(prev_candidates) if prev_candidates else None

    masses: list[BalanceMass] = []
    partial = False
    for mass in MASS_ORDER:
        resolved, mass_partial = _resolve_mass(mass, numeric, year, prev_year)
        masses.append(resolved)
        partial = partial or mass_partial

    unmapped: dict[str, list[BalanceLine]] = {"assets": [], "liabilities": []}
    # Totals and reported subtotals resolve above — never as "other" lines.
    resolved_concepts = set(TOTAL_CONCEPTS["total_assets"]) | set(
        TOTAL_CONCEPTS["total_liabilities"]
    )
    for subtotal_list in MASS_SUBTOTAL_CONCEPTS.values():
        resolved_concepts.update(subtotal_list)
    # Unmapped *extras* are shown separately but are not "missing data" —
    # ``partial`` is reserved for lines/totals the filing leaves out.
    for concept, years_values in numeric.items():
        if concept in resolved_concepts:
            continue
        if is_memorandum(concept) or not is_monetary(units.get(concept, "")):
            continue
        if concept_mass(concept) is not None:
            continue
        column = _unmapped_column(concept)
        unmapped[column].append(
            BalanceLine(concept, human_label(concept), years_values.get(year), None)
        )

    by_key = {mass.key: mass for mass in masses}
    total_assets, assets_reported = _resolve_total("total_assets", numeric, year)
    if total_assets is None:
        current = by_key["assets_current"].subtotal
        noncurrent = by_key["assets_noncurrent"].subtotal
        if current is not None and noncurrent is not None:
            total_assets = current + noncurrent
    total_liabilities, liab_reported = _resolve_total("total_liabilities", numeric, year)
    if total_liabilities is None:
        current = by_key["liab_current"].subtotal
        noncurrent = by_key["liab_noncurrent"].subtotal
        if current is not None and noncurrent is not None:
            total_liabilities = current + noncurrent
    equity_mass = by_key["equity"]
    total_equity = equity_mass.subtotal
    equity_reported = equity_mass.subtotal_reported

    delta: float | None = None
    balanced: bool | None = None
    if None not in (total_assets, total_liabilities, total_equity):
        delta = float(total_assets) - float(total_liabilities) - float(total_equity)
        tolerance = max(
            BALANCE_TOLERANCE_MIN, BALANCE_TOLERANCE_RATIO * abs(float(total_assets))
        )
        balanced = abs(delta) <= tolerance
    else:
        partial = True

    memoranda = [
        BalanceLine(concept, human_label(concept), values.get(year), None)
        for concept, values in sorted(numeric.items())
        if is_memorandum(concept)
    ]

    currency = "USD"
    for concept in TOTAL_CONCEPTS["total_assets"]:
        if units.get(concept):
            currency = units[concept]
            break

    return BalanceModel(
        year=year,
        currency=currency,
        masses=masses,
        other_assets=unmapped["assets"],
        other_liabilities=unmapped["liabilities"],
        total_assets=total_assets,
        total_assets_reported=assets_reported,
        total_liabilities=total_liabilities,
        total_liabilities_reported=liab_reported,
        total_equity=total_equity,
        total_equity_reported=equity_reported,
        delta=delta,
        balanced=balanced,
        partial=partial,
        memoranda=memoranda,
    )


def _resolve_total(
    key: str, numeric: dict[str, dict[int, float]], year: int
) -> tuple[float | None, bool]:
    found = _first_present(TOTAL_CONCEPTS[key], numeric, year)
    if found is None:
        return None, False
    return found[1], True


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def _arrow_span(delta: float | None) -> str:
    """▲/▼ with an explicit sign — color is never the only signal."""
    if delta is None:
        return DASH
    if delta > 0:
        return '<span class="vi-bs-up">▲ +</span>'
    if delta < 0:
        return '<span class="vi-bs-down">▼ −</span>'
    return "– "


def _lines_table(
    mass: BalanceMass,
    model: BalanceModel,
    scale: str,
    with_percent: bool,
    with_yoy: bool,
) -> str:
    unit = model.currency
    headers = '<th class="vi-bs-label">Line item</th>'
    headers += f'<th class="vi-bs-num">FY{model.year}</th>'
    if with_percent:
        headers += '<th class="vi-bs-num">% of mass</th>'
    if with_yoy:
        headers += '<th class="vi-bs-num">YoY</th>'
    rows = [f"<tr>{headers}</tr>"]

    for line in mass.lines:
        cells = [
            f'<td class="vi-bs-label" title="{escape(line.concept)}">{escape(line.label)}</td>',
            f'<td class="vi-bs-num">{escape(fmt_money(line.value, unit, scale=scale))}</td>',
        ]
        if with_percent:
            fraction = None
            if line.value is not None and mass.subtotal:
                fraction = line.value / mass.subtotal
            cells.append(f'<td class="vi-bs-num">{escape(fmt_pct(fraction))}</td>')
        if with_yoy:
            if line.value is not None and line.prev_value:
                change = (line.value - line.prev_value) / abs(line.prev_value)
                cells.append(
                    f'<td class="vi-bs-num">{_arrow_span(change)}'
                    f'{escape(fmt_pct(change))}</td>'
                )
            else:
                cells.append(f'<td class="vi-bs-num">{DASH}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")

    marker = "" if mass.subtotal_reported else "*"
    total_cells = [
        f'<td class="vi-bs-label">{escape(mass.label)}{marker}</td>',
        f'<td class="vi-bs-num">{escape(fmt_money(mass.subtotal, unit, scale=scale))}</td>',
    ]
    if with_percent:
        total_cells.append('<td class="vi-bs-num">100.0%</td>')
    if with_yoy:
        total_cells.append(f'<td class="vi-bs-num">{DASH}</td>')
    rows.append(f'<tr class="vi-bs-subtotal">{"".join(total_cells)}</tr>')

    computed = "" if mass.subtotal_reported else "computed"
    aria = f"Subtotal {computed} de {mass.label}".strip()
    return f'<table class="vi-bs-lines" role="table" aria-label="{escape(aria)}">' + "".join(rows) + "</table>"


def _other_block(lines: list[BalanceLine], model: BalanceModel, scale: str) -> str:
    if not lines:
        return ""
    rows = [
        f'<tr><td class="vi-bs-label" title="{escape(line.concept)}">{escape(line.label)}</td>'
        f'<td class="vi-bs-num">{escape(fmt_money(line.value, model.currency, scale=scale))}</td></tr>'
        for line in lines
    ]
    return (
        '<div class="vi-bs-other">'
        '<div class="vi-bs-other-title" role="heading" aria-level="3">'
        "Other items (unclassified)</div>"
        '<table class="vi-bs-lines" role="table" aria-label="Other items unclassified">'
        + "".join(rows)
        + "</table></div>"
    )


def _memoranda_unit(line: BalanceLine, units: dict[str, str]) -> str:
    """Abbreviate memoranda in their own unit (shares stay ``sh``, public
    float is money) instead of forcing ``shares``."""
    unit = units.get(line.concept, "")
    return unit or "shares"


def _total_row(
    text: str, value: float | None, model: BalanceModel, scale: str, computed: bool
) -> str:
    marker = "*" if computed else ""
    rendered = fmt_money(value, model.currency, scale=scale)
    return (
        f'<div class="vi-bs-total">'
        f'<span class="vi-bs-total-label">{escape(text)}{marker}</span>'
        f'<span class="vi-bs-num">{escape(rendered)}</span></div>'
    )


def render_balance_sheet(
    numeric: dict[str, dict[int, float]],
    units: dict[str, str],
    years: list[int],
    year: int,
    *,
    ticker: str,
    source: str,
) -> None:
    """Render the T balance for ``year`` with scale selector and balance chip."""
    model = build_balance_model(numeric, units, year, years)

    head_left, head_right = st.columns([3, 1])
    head_left.caption(
        f"Balance — FY{year} · {model.currency} · source: {source}"
        + (" · partial data" if model.partial else "")
    )
    with head_right:
        scale_label = st.selectbox(
            "Scale",
            list(SCALE_CHOICES),
            key=f"bs_scale_{ticker}_{year}",
            label_visibility="collapsed",
        )
    scale = SCALE_CHOICES[scale_label]

    toggle_a, toggle_b, _spacer = st.columns([1, 1, 3])
    with toggle_a:
        with_percent = st.checkbox("% of mass", key=f"bs_pct_{ticker}_{year}")
    with toggle_b:
        with_yoy = st.checkbox(
            "YoY change", key=f"bs_yoy_{ticker}_{year}", disabled=len(years) < 2
        )

    left_column, right_column = st.columns(2)
    with left_column:
        st.markdown('<div class="vi-bs-head">ASSETS</div>', unsafe_allow_html=True)
        for mass in model.masses:
            if MASS_COLUMN[mass.key] != "assets":
                continue
            with st.expander(
                f"{mass.label} · {fmt_money(mass.subtotal, model.currency, scale=scale)}",
                expanded=mass.key == "assets_current",
            ):
                st.markdown(
                    _lines_table(mass, model, scale, with_percent, with_yoy),
                    unsafe_allow_html=True,
                )
        st.markdown(_other_block(model.other_assets, model, scale), unsafe_allow_html=True)
        st.markdown(
            _total_row(
                "TOTAL ASSETS",
                model.total_assets,
                model,
                scale,
                computed=not model.total_assets_reported,
            ),
            unsafe_allow_html=True,
        )
    with right_column:
        st.markdown(
            '<div class="vi-bs-head">LIABILITIES + EQUITY</div>', unsafe_allow_html=True
        )
        for mass in model.masses:
            if MASS_COLUMN[mass.key] != "liabilities":
                continue
            with st.expander(
                f"{mass.label} · {fmt_money(mass.subtotal, model.currency, scale=scale)}",
                expanded=mass.key == "liab_current",
            ):
                st.markdown(
                    _lines_table(mass, model, scale, with_percent, with_yoy),
                    unsafe_allow_html=True,
                )
        st.markdown(
            _other_block(model.other_liabilities, model, scale), unsafe_allow_html=True
        )
        right_total = None
        if model.total_liabilities is not None and model.total_equity is not None:
            right_total = model.total_liabilities + model.total_equity
        st.markdown(
            _total_row(
                "TOTAL LIABILITIES + EQUITY",
                right_total,
                model,
                scale,
                computed=not (
                    model.total_liabilities_reported and model.total_equity_reported
                ),
            ),
            unsafe_allow_html=True,
        )

    if model.balanced is True:
        st.success(f"✓ Balanced (Δ = {fmt_delta(model.delta, model.currency, scale=scale)})")
    elif model.balanced is False:
        st.error(
            "Does not balance — data possibly incomplete · "
            f"Δ = {fmt_delta(model.delta, model.currency, scale=scale)}"
        )
    else:
        st.info(
            "Partial balance — totals missing to verify "
            "(data possibly incomplete)"
        )

    memoranda_text = " · ".join(
        f"{line.label}: {abbreviate_number(line.value, _memoranda_unit(line, units))}"
        for line in model.memoranda
        if line.value is not None
    )
    if memoranda_text:
        st.caption(f"Memorandum note (not part of the balance) · {memoranda_text}")
    st.caption(
        "* Subtotal computed from the line items when the filing "
        "does not report it."
    )
