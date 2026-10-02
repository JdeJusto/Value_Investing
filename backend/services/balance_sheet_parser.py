"""Extract the balance sheet from a 10-K/10-Q document (HTML).

Strategy (see ``docs/filings_extraction.md``): **anchors first**, then a
**hybrid fallback** that scans tables for one containing both "Total assets"
and "Total liabilities" — the real 2024 10-Ks carry no ``<a name>`` anchors
at all, so the fallback is the working path for modern filings.

Values keep the **original formatting** ("$29,943", "( 7,172 )"): the point
is to read the source, not to normalise it. Nothing is fetched here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

#: Legacy filings anchor their statements; modern ones do not.
ANCHOR_CANDIDATES: tuple[str, ...] = (
    "s_balance_sheet",
    "s_consolidated_balance_sheets",
    "consolidated_balance_sheets",
    "consolidated_balance_sheet",
    "balance_sheets",
    "balance_sheet",
    "s_bs",
)

_CURRENCY = {"$", "€", "£", "¥", "usd"}
_WS = re.compile(r"\s+")
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def _looks_like_period_row(cells: list[str]) -> bool:
    """True for the header row carrying the two period labels."""
    if len(cells) < 2:
        return False
    joined = " ".join(cells).lower()
    if "$" in joined or "€" in joined:
        return False
    return any(month in joined for month in _MONTHS)


@dataclass(frozen=True)
class BalanceSheetLine:
    """One line, with the two period columns as rendered in the filing."""

    label: str
    current: str | None
    prior: str | None
    indent_level: int = 0


@dataclass
class BalanceSheet:
    lines: list[BalanceSheetLine]
    source: str  # "anchors" | "fallback"
    filing_date: date | None = None
    period_end: date | None = None
    form_type: str | None = None
    extraction_warnings: list[str] = field(default_factory=list)

    @property
    def header_periods(self) -> tuple[str | None, str | None]:
        """(current, prior) period labels, taken from the header row if any."""
        return getattr(self, "_periods", (None, None))

    def as_rows(self) -> list[dict[str, Any]]:
        """Plain rows for a dataframe/table renderer."""
        current, prior = self.header_periods
        return [
            {
                "Line item": ("  " * line.indent_level) + line.label,
                current or "Current": line.current or "",
                prior or "Prior": line.prior or "",
            }
            for line in self.lines
        ]


def _clean(text: str) -> str:
    text = _WS.sub(" ", text or "").strip()
    # "( 7,172 )" reads better as "(7,172)"; the digits are untouched.
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    return text


def _row_cells(row: Any) -> list[str]:
    cells = [
        _clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])
    ]
    return [cell for cell in cells if cell]


def _split_values(cells: list[str]) -> list[str]:
    """Merge a standalone currency symbol into the number that follows it.

    Filings render ``$`` and the amount in separate cells
    (``['$', '29,943', '$', '29,965']``), other rows keep them together
    (``['35,228', '31,590']``); both become ``['$29,943', '$29,965']`` and
    ``['35,228', '31,590']``.
    """
    values: list[str] = []
    pending_currency: str | None = None
    for cell in cells:
        if cell.lower() in _CURRENCY:
            pending_currency = cell
            continue
        values.append(f"{pending_currency}{cell}" if pending_currency else cell)
        pending_currency = None
    return values


def _indent_level(row: Any) -> int:
    """Best-effort indentation from the label cell's padding, else 0."""
    cell = row.find(["td", "th"])
    if cell is None:
        return 0
    style = f"{cell.get('style') or ''}"
    match = re.search(r"padding-left\s*:\s*([0-9.]+)", style, flags=re.IGNORECASE)
    if match:
        return min(int(float(match.group(1)) // 10), 4)
    return 0


class BalanceSheetParser:
    """HTML → :class:`BalanceSheet` (None when nothing usable is found)."""

    def parse(
        self,
        html: str,
        filing_date: date | None = None,
        period_end: date | None = None,
        form_type: str | None = None,
    ) -> BalanceSheet | None:
        if not html:
            return None
        try:
            from bs4 import BeautifulSoup
        except ImportError:  # pragma: no cover — bs4 is a declared dependency
            return None
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:  # noqa: BLE001 — malformed input must not raise
            return None

        table = self._table_from_anchors(soup)
        source = "anchors"
        warnings: list[str] = []
        if table is None:
            table = self._table_from_content(soup)
            source = "fallback"
            if table is None:
                return None
            warnings.append(
                "no balance-sheet anchor matched; selected the table "
                "containing 'Total assets' and 'Total liabilities'"
            )

        lines, periods = self._lines_from_table(table)
        if not lines:
            return None
        sheet = BalanceSheet(
            lines=lines,
            source=source,
            filing_date=filing_date,
            period_end=period_end,
            form_type=form_type,
            extraction_warnings=warnings,
        )
        sheet._periods = periods  # type: ignore[attr-defined]
        return sheet

    # ------------------------------------------------------------------
    @staticmethod
    def _table_from_anchors(soup: Any) -> Any:
        wanted = {name.lower() for name in ANCHOR_CANDIDATES}
        for anchor in soup.find_all("a"):
            name = str(anchor.get("name") or anchor.get("id") or "").lower()
            if name in wanted:
                table = anchor.find_next("table")
                if table is not None:
                    return table
        return None

    @staticmethod
    def _table_from_content(soup: Any) -> Any:
        for table in soup.find_all("table"):
            text = table.get_text(" ", strip=True).lower()
            if "total assets" in text and "total liabilities" in text:
                return table
        return None

    def _lines_from_table(self, table: Any) -> tuple[list[BalanceSheetLine], tuple]:
        lines: list[BalanceSheetLine] = []
        periods: tuple[str | None, str | None] = (None, None)
        for row in table.find_all("tr"):
            cells = _row_cells(row)
            if not cells:
                continue
            if _looks_like_period_row(cells):
                periods = (cells[-2], cells[-1])
                continue
            label = cells[0]
            values = _split_values(cells[1:])
            if not values and len(cells) > 1:
                continue
            lines.append(
                BalanceSheetLine(
                    label=label,
                    current=values[0] if values else None,
                    prior=values[1] if len(values) > 1 else None,
                    indent_level=_indent_level(row),
                )
            )
        return lines, periods
