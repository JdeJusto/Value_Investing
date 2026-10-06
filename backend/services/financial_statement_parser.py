"""Extract financial statements from 10-K/10-Q documents (HTML).

Generalizes the v0.6.0 balance-sheet parser to three statement types
(``BALANCE_SHEET``, ``INCOME_STATEMENT``, ``CASH_FLOW``). Strategy per type:
**anchors first** (legacy filings), then a **content fallback** that picks the
largest table matching the type's required pair of labels — modern filings
carry no ``<a name>`` anchors at all, so the fallback is the working path.

Values keep the **original formatting** ("$39,544", "( 7,172 )"): the point
is to read the source, not to normalise it. Parsed statements can be cached
as JSON next to the raw HTML (see :func:`load_financial_statement`).

``backend/services/balance_sheet_parser.py`` re-exports the v0.6.0 names for
backward compatibility.
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

#: Bump when the parser logic changes in a way that alters the output; every
#: JSON cache with a different version is ignored and re-parsed.
PARSER_VERSION = 2

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


class StatementType(str, Enum):
    """The three statements this parser understands."""

    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"

    @property
    def label(self) -> str:
        return {
            StatementType.BALANCE_SHEET: "Balance Sheet",
            StatementType.INCOME_STATEMENT: "Income Statement",
            StatementType.CASH_FLOW: "Cash Flow",
        }[self]


#: Per-type anchors (legacy filings), statement titles (modern filings) and
#: required label pairs (fallback).
STATEMENT_SIGNATURES: dict[StatementType, dict[str, Any]] = {
    StatementType.BALANCE_SHEET: {
        "anchors": [
            "s_balance_sheet",
            "s_consolidated_balance_sheets",
            "consolidated_balance_sheets",
            "consolidated_balance_sheet",
            "balance_sheets",
            "balance_sheet",
            "s_bs",
        ],
        "titles": [
            "balance sheets",
            "balance sheet",
        ],
        "required_pairs": [
            ["total assets", "total liabilities"],
            ["total assets", "shareholders' equity"],
            ["total assets", "stockholders' equity"],
        ],
    },
    StatementType.INCOME_STATEMENT: {
        "anchors": [
            "s_income_statement",
            "consolidated_statements_of_operations",
            "consolidated_statements_of_income",
            "s_statements_of_operations",
            "statements_of_operations",
            "income_statement",
        ],
        "titles": [
            "statements of operations",
            "statement of operations",
            "statements of income",
            "statement of income",
            "statements of earnings",
            "statement of earnings",
        ],
        "required_pairs": [
            ["net income", "revenue"],
            ["net income", "total revenue"],
            ["net income", "net sales"],
            ["net income", "total net sales"],
            ["net loss", "revenue"],
            # Filers that label the bottom line "Net (loss) income" (COLD and
            # other loss-making quarters) contain neither "net income" nor
            # "net loss" as a contiguous phrase.
            ["net (loss) income", "revenue"],
            ["net (loss) income", "total revenue"],
            ["net (loss) income", "net sales"],
            # JNJ (and other filers) label the bottom line "Net earnings".
            ["net earnings", "revenue"],
            ["net earnings", "total revenue"],
            ["net earnings", "net sales"],
            ["net earnings", "total net sales"],
            # JNJ labels the top line "Sales to customers".
            ["net earnings", "sales to customers"],
            ["net income", "sales to customers"],
        ],
    },
    StatementType.CASH_FLOW: {
        "anchors": [
            "s_cash_flow",
            "consolidated_statements_of_cash_flows",
            "statements_of_cash_flows",
            "cash_flow_statement",
        ],
        "titles": [
            "statements of cash flows",
            "statement of cash flows",
        ],
        "required_pairs": [
            ["net cash", "operating activities"],
            ["cash and cash equivalents", "investing activities"],
            ["operating activities", "investing activities"],
            ["net cash provided", "financing activities"],
        ],
    },
}


@dataclass(frozen=True)
class StatementLine:
    """One line, with the two period columns as rendered in the filing."""

    label: str
    current: str | None
    prior: str | None
    indent_level: int = 0


@dataclass
class Statement:
    statement_type: StatementType
    lines: list[StatementLine]
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
    """Merge a standalone currency symbol into the number that follows it."""
    values: list[str] = []
    pending_currency: str | None = None
    for cell in cells:
        if cell.lower() in _CURRENCY:
            pending_currency = cell
            continue
        values.append(f"{pending_currency}{cell}" if pending_currency else cell)
        pending_currency = None
    return values


def _looks_like_period_row(cells: list[str]) -> bool:
    if len(cells) < 2:
        return False
    joined = " ".join(cells).lower()
    if "$" in joined or "€" in joined:
        return False
    return any(month in joined for month in _MONTHS)


def _indent_level(row: Any) -> int:
    cell = row.find(["td", "th"])
    if cell is None:
        return 0
    style = f"{cell.get('style') or ''}"
    match = re.search(r"padding-left\s*:\s*([0-9.]+)", style, flags=re.IGNORECASE)
    if match:
        return min(int(float(match.group(1)) // 10), 4)
    return 0


class FinancialStatementParser:
    """HTML → :class:`Statement` (None when nothing usable is found)."""

    def parse(
        self,
        html: str,
        statement_type: StatementType = StatementType.BALANCE_SHEET,
        filing_date: date | None = None,
        period_end: date | None = None,
        form_type: str | None = None,
    ) -> Statement | None:
        if not isinstance(statement_type, StatementType):
            try:
                statement_type = StatementType(statement_type)
            except ValueError as exc:
                raise ValueError(
                    f"unknown statement type {statement_type!r}; "
                    f"expected one of {[t.value for t in StatementType]}"
                ) from exc
        if not html:
            return None
        try:
            from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")
        except Exception:  # noqa: BLE001 — malformed input must not raise
            return None

        table = self._table_from_anchors(soup, statement_type)
        source = "anchors"
        extraction_warnings: list[str] = []
        if table is None:
            table = self._table_from_content(soup, statement_type)
            source = "fallback"
            if table is None:
                return None
            pairs = STATEMENT_SIGNATURES[statement_type]["required_pairs"][0]
            extraction_warnings.append(
                f"no {statement_type.value} anchor matched; selected the "
                f"largest table containing {pairs[0]!r} and {pairs[1]!r}"
            )

        lines, periods = self._lines_from_table(table)
        if not lines:
            return None
        statement = Statement(
            statement_type=statement_type,
            lines=lines,
            source=source,
            filing_date=filing_date,
            period_end=period_end,
            form_type=form_type,
            extraction_warnings=extraction_warnings,
        )
        statement._periods = periods  # type: ignore[attr-defined]
        return statement

    # ------------------------------------------------------------------
    @staticmethod
    def _table_from_anchors(soup: Any, statement_type: StatementType) -> Any:
        wanted = {
            name.lower() for name in STATEMENT_SIGNATURES[statement_type]["anchors"]
        }
        for anchor in soup.find_all("a"):
            name = str(anchor.get("name") or anchor.get("id") or "").lower()
            if name in wanted:
                table = anchor.find_next("table")
                if table is not None:
                    return table
        return None

    @staticmethod
    def _table_from_content(soup: Any, statement_type: StatementType) -> Any:
        """Largest table whose text contains one of the required pairs.

        A statement title (``titles`` in the signature) wins over raw size:
        a balance sheet can contain a required pair by accident (COLD's
        balance sheet carries "net earnings" and "revenue", so the income
        signature used to select it), while only the real income statement
        says "statements of operations".
        """
        signature = STATEMENT_SIGNATURES[statement_type]
        titles = tuple(title.lower() for title in signature.get("titles", ()))
        best = None
        best_size = 0
        best_titled = None
        best_titled_size = 0
        for table in soup.find_all("table"):
            text = table.get_text(" ", strip=True).lower()
            if not any(
                all(needle in text for needle in pair)
                for pair in signature["required_pairs"]
            ):
                continue
            size = len(text)
            if size > best_size:
                best, best_size = table, size
            if (
                titles
                and any(title in text for title in titles)
                and size > best_titled_size
            ):
                best_titled, best_titled_size = table, size
        return best_titled if best_titled is not None else best

    def _lines_from_table(self, table: Any) -> tuple[list[StatementLine], tuple]:
        lines: list[StatementLine] = []
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
                StatementLine(
                    label=label,
                    current=values[0] if values else None,
                    prior=values[1] if len(values) > 1 else None,
                    indent_level=_indent_level(row),
                )
            )
        return lines, periods


# ---------------------------------------------------------------------------
# Orchestration: demo fixture, parse cache, or fetch + parse
# ---------------------------------------------------------------------------
def _demo_statement_path(record: Any, statement_type: StatementType) -> Path:
    from backend.services.demo_mode import DEMO_ROOT

    period = (
        record.period_of_report.isoformat()
        if getattr(record, "period_of_report", None)
        else "unknown"
    )
    base = DEMO_ROOT
    ticker = getattr(record, "ticker", "UNKNOWN")
    form = getattr(record, "form_type", "10-K")
    new = base / "statements" / f"{ticker}_{statement_type.value}_{period}.json"
    if new.exists():
        return new
    # v0.6.0 layout (balance sheets only).
    legacy = base / "balance_sheets" / f"{ticker}_{form}_{period}.json"
    return legacy if legacy.exists() else new


def _statement_from_payload(
    payload: dict, statement_type: StatementType, record: Any
) -> Statement:
    statement = Statement(
        statement_type=statement_type,
        lines=[
            StatementLine(
                label=line.get("label", ""),
                current=line.get("current"),
                prior=line.get("prior"),
                indent_level=int(line.get("indent_level") or 0),
            )
            for line in payload.get("lines", [])
        ],
        source=str(payload.get("source", "demo")),
        filing_date=getattr(record, "filing_date", None),
        period_end=getattr(record, "period_of_report", None),
        form_type=getattr(record, "form_type", None),
        extraction_warnings=list(payload.get("extraction_warnings", [])),
    )
    statement._periods = tuple(payload.get("periods") or (None, None))  # type: ignore[attr-defined]
    return statement


def statement_cache_path(
    cache_dir: str | Path,
    cik: str,
    accession: str,
    document: str | None,
    statement_type: StatementType,
) -> Path:
    """``<doc>.<statement_type>.json`` next to the cached HTML."""
    cik_no_zeros = str(int(cik)) if str(cik).isdigit() else str(cik)
    name = document or "document.htm"
    return (
        Path(cache_dir)
        / cik_no_zeros
        / accession.replace("-", "")
        / (f"{name}.{statement_type.value}.json")
    )


def _read_statement_cache(path: Path) -> Statement | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if int(payload.get("version", 0)) != PARSER_VERSION:
        return None
    try:
        statement_type = StatementType(payload["statement_type"])
    except (KeyError, ValueError):
        return None
    record = type("_R", (), {})()
    record.filing_date = (
        date.fromisoformat(payload["filing_date"])
        if payload.get("filing_date")
        else None
    )
    record.period_of_report = (
        date.fromisoformat(payload["period_end"]) if payload.get("period_end") else None
    )
    record.form_type = payload.get("form_type")
    return _statement_from_payload(payload, statement_type, record)


def _write_statement_cache(path: Path, statement: Statement) -> None:
    payload = {
        "version": PARSER_VERSION,
        "statement_type": statement.statement_type.value,
        "filing_date": statement.filing_date.isoformat()
        if statement.filing_date
        else None,
        "period_end": statement.period_end.isoformat()
        if statement.period_end
        else None,
        "form_type": statement.form_type,
        "source": statement.source,
        "periods": list(statement.header_periods),
        "extraction_warnings": statement.extraction_warnings,
        "lines": [
            {
                "label": line.label,
                "current": line.current,
                "prior": line.prior,
                "indent_level": line.indent_level,
            }
            for line in statement.lines
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError:
        pass  # a read-only cache dir must not break the parse


def clear_statement_cache(
    cache_dir: str | Path = "data/raw/filings",
    statement_type: StatementType | None = None,
) -> int:
    """Delete cached parsed statements (JSON only); the HTML is kept."""
    pattern = (
        f"*.{statement_type.value}.json" if statement_type is not None else "*.json"
    )
    removed = 0
    for path in Path(cache_dir).rglob(pattern):
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def load_financial_statement(
    record: Any,
    statement_type: StatementType = StatementType.BALANCE_SHEET,
    fetcher: Any = None,
    cache_dir: str | Path = "data/raw/filings",
) -> Statement | None:
    """Statement for a :class:`FilingRecord`, cached at every level.

    Order: demo fixture (offline) → parsed JSON cache → fetch HTML (cached)
    and parse. Never raises: any failure returns None.
    """
    from backend.services.demo_mode import is_demo

    if is_demo():
        path = _demo_statement_path(record, statement_type)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        statement = _statement_from_payload(payload, statement_type, record)
        return statement if statement.lines else None

    cik = getattr(record, "cik", "")
    accession = getattr(record, "accession_number", "")
    document = getattr(record, "primary_document", None)

    cache_path = statement_cache_path(
        cache_dir, cik, accession, document, statement_type
    )
    cached = _read_statement_cache(cache_path)
    if cached is not None:
        return cached

    if fetcher is None:
        from backend.services.filing_fetcher import FilingFetcher

        fetcher = FilingFetcher(cache_dir=cache_dir)
    html = fetcher.fetch_html(cik, accession, document)
    if html is None:
        return None
    statement = FinancialStatementParser().parse(
        html,
        statement_type,
        filing_date=getattr(record, "filing_date", None),
        period_end=getattr(record, "period_of_report", None),
        form_type=getattr(record, "form_type", None),
    )
    if statement is not None:
        _write_statement_cache(cache_path, statement)
    return statement
