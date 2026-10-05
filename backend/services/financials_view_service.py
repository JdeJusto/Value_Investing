"""Full financials view: every FDB fact, grouped by statement, per fiscal year.

Reads ``financial_facts`` through the repository (all XBRL concepts, not just
the mapped VO fields), classifies each concept into Balance Sheet / Income
Statement / Cash Flow / Other, dedupes to one value per (concept, fiscal year)
and formats values with the statement convention ("$29,943", "(7,172)").

Pure view-model: no Streamlit, no network, no normalization to floats. The UI
renders this in the "Financials" tab; the sidebar is reserved for a future
alerts panel (see ``docs/backlog.md``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from backend.repositories.fdb_concept_mapping import (
    BALANCE_SHEET_CONCEPTS,
    CASH_FLOW_CONCEPTS,
    INCOME_STATEMENT_CONCEPTS,
)
from backend.services.demo_mode import DEMO_ROOT, is_demo
from backend.services.ui_format import abbreviate_number

#: Default history window and its hard cap (the UI offers 1..20 years).
DEFAULT_MAX_YEARS = 15
MAX_YEARS_CAP = 20

#: Soft guidance: above this many facts the view warns. It never truncates
#: rows (a silent cut would drop whole concepts); narrow the years instead.
FACTS_GUIDANCE_THRESHOLD = 5_000

#: Curated labels for the most common concepts (fallback: CamelCase split).
CONCEPT_LABELS: dict[str, str] = {
    "NetIncomeLoss": "Net Income",
    "Revenues": "Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": (
        "Revenue from Contract with Customer, Excluding Assessed Tax"
    ),
    "GrossProfit": "Gross Profit",
    "OperatingIncomeLoss": "Operating Income",
    "OperatingExpenses": "Operating Expenses",
    "NonoperatingIncomeExpense": "Nonoperating Income (Expense)",
    "CostOfGoodsAndServicesSold": "Cost of Goods and Services Sold",
    "ResearchAndDevelopmentExpense": "Research and Development Expense",
    "SellingGeneralAndAdministrativeExpense": (
        "Selling, General and Administrative Expense"
    ),
    "EarningsPerShareDiluted": "Earnings Per Share (Diluted)",
    "EarningsPerShareBasic": "Earnings Per Share (Basic)",
    "WeightedAverageNumberOfSharesOutstandingBasic": (
        "Weighted Average Shares Outstanding (Basic)"
    ),
    "WeightedAverageNumberOfDilutedSharesOutstanding": (
        "Weighted Average Shares Outstanding (Diluted)"
    ),
    "IncomeTaxExpenseBenefit": "Income Tax Expense (Benefit)",
    "IncomeTaxesPaidNet": "Income Taxes Paid, Net",
    "Assets": "Total Assets",
    "AssetsCurrent": "Current Assets",
    "OtherAssetsCurrent": "Other Assets (Current)",
    "OtherAssetsNoncurrent": "Other Assets (Noncurrent)",
    "Liabilities": "Total Liabilities",
    "LiabilitiesCurrent": "Current Liabilities",
    "OtherLiabilitiesNoncurrent": "Other Liabilities (Noncurrent)",
    "LiabilitiesAndStockholdersEquity": "Liabilities and Stockholders' Equity",
    "StockholdersEquity": "Stockholders' Equity",
    "RetainedEarningsAccumulatedDeficit": "Retained Earnings (Accumulated Deficit)",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": (
        "Accumulated Other Comprehensive Income (Loss), Net of Tax"
    ),
    "CashAndCashEquivalentsAtCarryingValue": "Cash and Cash Equivalents",
    "InventoryNet": "Inventory, Net",
    "AccountsReceivableNetCurrent": "Accounts Receivable, Net (Current)",
    "AccountsPayableCurrent": "Accounts Payable (Current)",
    "CommonStockSharesOutstanding": "Common Stock Shares Outstanding",
    "CommonStockSharesIssued": "Common Stock Shares Issued",
    "CommonStockSharesAuthorized": "Common Stock Shares Authorized",
    "ComprehensiveIncomeNetOfTax": "Comprehensive Income, Net of Tax",
    "ShareBasedCompensation": "Share-Based Compensation",
    "NetCashProvidedByUsedInOperatingActivities": (
        "Net Cash Provided by Operating Activities"
    ),
    "NetCashProvidedByUsedInInvestingActivities": (
        "Net Cash Provided by Investing Activities"
    ),
    "NetCashProvidedByUsedInFinancingActivities": (
        "Net Cash Provided by Financing Activities"
    ),
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": (
        "Cash, Cash Equivalents and Restricted Cash"
    ),
    "PaymentsToAcquirePropertyPlantAndEquipment": (
        "Payments to Acquire Property, Plant and Equipment"
    ),
    "IncreaseDecreaseInInventories": "Increase (Decrease) in Inventories",
    "IncreaseDecreaseInAccountsPayable": "Increase (Decrease) in Accounts Payable",
    "IncreaseDecreaseInAccountsReceivable": (
        "Increase (Decrease) in Accounts Receivable"
    ),
    "IncreaseDecreaseInOtherOperatingAssets": (
        "Increase (Decrease) in Other Operating Assets"
    ),
    "IncreaseDecreaseInOtherOperatingLiabilities": (
        "Increase (Decrease) in Other Operating Liabilities"
    ),
    "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities": (
        "Proceeds from Maturities/Prepayments/Calls of Available-for-Sale Securities"
    ),
    "PaymentsForProceedsFromOtherInvestingActivities": (
        "Payments for (Proceeds from) Other Investing Activities"
    ),
    "EntityCommonStockSharesOutstanding": "Entity Common Stock Shares Outstanding",
    "EntityPublicFloat": "Entity Public Float",
}


def humanize_concept(concept: str) -> str:
    """XBRL tag -> readable label ("NetIncomeLoss" -> "Net Income").

    A curated dict covers the most common concepts; the fallback splits
    CamelCase (keeping acronym runs like ``EBITDA`` intact) and strips
    namespace prefixes (``us-gaap:`` / ``ifrs-full:``).
    """
    raw = (concept or "").rsplit(":", 1)[-1]
    if raw in CONCEPT_LABELS:
        return CONCEPT_LABELS[raw]
    if not raw:
        return ""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    spaced = spaced.replace("_", " ").replace("-", " ")
    return spaced[:1].upper() + spaced[1:]


def classify_concept(concept: str) -> str:
    """One of ``balance_sheet`` / ``income_statement`` / ``cash_flow`` / ``other``.

    Curated repository mappings win first; then strong family heuristics
    (cash-flow Activities/Payments/Proceeds/IncreaseDecrease and income
    Revenues/EarningsPerShare/Amortization/Impairment) before the balance
    sheet name heuristics, so e.g. ``PaymentsToAcquireIntangibleAssets`` is
    cash flow despite containing "Asset". Everything else is ``other`` so
    nothing is ever dropped from the view.
    """
    if concept in BALANCE_SHEET_CONCEPTS:
        return "balance_sheet"
    if concept in INCOME_STATEMENT_CONCEPTS:
        return "income_statement"
    if concept in CASH_FLOW_CONCEPTS:
        return "cash_flow"
    # Strong cash-flow families.
    if (
        "OperatingActivities" in concept
        or "InvestingActivities" in concept
        or "FinancingActivities" in concept
    ):
        return "cash_flow"
    if concept.startswith(("Payments", "ProceedsFrom", "IncreaseDecrease")):
        return "cash_flow"
    # Strong income families.
    if concept.startswith(
        ("Revenues", "Revenue", "Sales", "EarningsPerShare", "ComprehensiveIncome")
    ) or concept.endswith("Revenue"):
        return "income_statement"
    if concept.startswith(("Amortization", "Impairment", "IncomeTaxReconciliation")):
        return "income_statement"
    # Balance sheet name heuristics.
    if concept.startswith("Assets") or "Asset" in concept:
        return "balance_sheet"
    if "Liabilities" in concept:
        return "balance_sheet"
    if concept.startswith(("StockholdersEquity", "Equity")):
        return "balance_sheet"
    return "other"


def format_fact_value(value: Any, unit: str) -> str:
    """FDB numeric -> statement convention ("$29,943", "(7,172)", "0.15").

    Currency gets a ``$`` prefix and thousands separators, negatives are
    parenthesized, per-share values keep two decimals, "pure" ratios keep up
    to four decimals. Always returns a string (never a float).
    """
    if value is None:
        return ""
    amount = Decimal(str(value))
    negative = amount < 0
    amount = abs(amount)
    integral = amount == amount.to_integral_value()
    if unit == "USD":
        text = f"${amount:,.0f}" if integral else f"${amount:,.2f}"
    elif unit == "USD/shares":
        text = f"${amount:,.2f}"
    elif unit == "shares":
        text = f"{amount:,.0f}" if integral else f"{amount:,.2f}"
    elif unit == "pure":
        text = f"{amount:,.4f}".rstrip("0").rstrip(".") or "0"
    else:
        text = f"{amount:,.0f}" if integral else f"{amount:,.2f}"
    return f"({text})" if negative else text


@dataclass(frozen=True)
class FinancialsRow:
    """One XBRL concept with its formatted value per fiscal year."""

    concept: str  # raw tag, e.g. "RevenueFromContractWithCustomer..."
    label: str  # humanized, e.g. "Revenue from Contract with Customer..."
    values: dict[int, str]  # fiscal_year -> formatted ("$29,943")
    unit: str  # "USD", "shares", "USD/shares", "pure", ...


@dataclass(frozen=True)
class FinancialsView:
    """Every stored fact for a company, bucketed by statement type."""

    ticker: str
    company_name: str
    fiscal_period: str
    years: list[int]  # available fiscal years, desc
    balance_sheet: list[FinancialsRow]
    income_statement: list[FinancialsRow]
    cash_flow: list[FinancialsRow]
    other: list[FinancialsRow]
    unmatched_count: int  # concepts not classified (they live in ``other``)
    extraction_warnings: list[str] = field(default_factory=list)


def table_rows(rows: list[FinancialsRow], years: list[int]) -> list[dict[str, str]]:
    """Dataframe-ready rows: Label | FY<year>... | Unit | Concept."""
    return [
        {
            "Label": row.label,
            **{f"FY{year}": row.values.get(year, "") for year in years},
            "Unit": row.unit,
            "Concept": row.concept,
        }
        for row in rows
    ]


def filter_rows(
    rows: list[FinancialsRow],
    query: str = "",
    units: set[str] | None = None,
) -> list[FinancialsRow]:
    """Client-side filter: label OR raw concept contains ``query`` (case
    insensitive), and the unit is in ``units`` when given."""
    needle = (query or "").strip().lower()
    kept: list[FinancialsRow] = []
    for row in rows:
        if units and row.unit not in units:
            continue
        if (
            needle
            and needle not in row.label.lower()
            and needle not in row.concept.lower()
        ):
            continue
        kept.append(row)
    return kept


def dedupe_facts(facts: list[dict], years: set[int]) -> dict[tuple[str, int], dict]:
    """One fact per (concept, fiscal_year): the latest ``period_end`` wins.

    FDB stores the comparative years embedded in each filing under the same
    fiscal-year bucket (FY2025 also carries period_end 2024-09-28), so the
    newest period_end is the value as of that year's own year-end. Shared by
    the Financials view and the insights panel so both read the same values.
    """
    ordered = sorted(
        facts,
        key=lambda fact: (
            str(fact.get("concept") or ""),
            -int(fact.get("fiscal_year") or 0),
            str(fact.get("period_end") or ""),
        ),
    )
    latest: dict[tuple[str, int], dict] = {}
    for fact in ordered:
        concept = str(fact.get("concept") or "")
        year = fact.get("fiscal_year")
        if not concept or year is None or int(year) not in years:
            continue
        key = (concept, int(year))
        candidate = str(fact.get("period_end") or "")
        current = latest.get(key)
        if current is None or candidate > str(current.get("period_end") or ""):
            latest[key] = fact
    return latest


def _concept_unit(year_facts: dict[int, dict]) -> str:
    for fact in year_facts.values():
        unit = str(fact.get("unit") or "")
        if unit:
            return unit
    return ""


def _rows_from_payload(rows: list[dict], years: list[int]) -> list[FinancialsRow]:
    """Demo fixtures already carry built rows (concept/label/values/unit)."""
    year_set = set(years)
    out: list[FinancialsRow] = []
    for row in rows:
        concept = str(row.get("concept") or "")
        values = {
            int(year): str(value)
            for year, value in (row.get("values") or {}).items()
            if int(year) in year_set
        }
        out.append(
            FinancialsRow(
                concept=concept,
                label=str(row.get("label") or humanize_concept(concept)),
                values=values,
                unit=str(row.get("unit") or ""),
            )
        )
    return out


class FinancialsViewService:
    """Builds the full Financials view from the repository (or demo fixtures)."""

    def __init__(self, repository: Any = None) -> None:
        self._repo = repository

    def _repository(self) -> Any:
        if self._repo is None:
            from backend.app.cli import build_financial_repository

            self._repo = build_financial_repository()
        return self._repo

    def fetch_facts(
        self,
        ticker: str,
        fiscal_period: str = "FY",
        max_years: int = DEFAULT_MAX_YEARS,
    ) -> list[dict]:
        """The raw fact rows the view (and the insights) read: one query."""
        repo = self._repository()
        if repo is None or not hasattr(repo, "list_all_facts"):
            return []
        return repo.list_all_facts(
            ticker.upper().strip(),
            (fiscal_period or "FY").upper(),
            max(1, min(int(max_years or DEFAULT_MAX_YEARS), MAX_YEARS_CAP)),
        )

    def build(
        self,
        ticker: str,
        fiscal_period: str = "FY",
        max_years: int = DEFAULT_MAX_YEARS,
        facts: list[dict] | None = None,
        abbreviate: bool = False,
    ) -> FinancialsView | None:
        """Full view, or ``None`` when the company has no stored facts.

        ``facts`` lets a caller that already fetched the rows (the UI loader,
        the demo-fixture script) build both the view and the insights from a
        single query; when omitted the repository is read here. ``abbreviate``
        is a display mode (K/M/B/T); the default keeps full precision.
        """
        ticker = (ticker or "").upper().strip()
        if not ticker:
            return None
        period = (fiscal_period or "FY").upper()
        years_cap = max(1, min(int(max_years or DEFAULT_MAX_YEARS), MAX_YEARS_CAP))
        if facts is None and is_demo():
            return self._demo_view(ticker, period, years_cap)

        if facts is None:
            facts = self.fetch_facts(ticker, period, years_cap)
        if not facts:
            return None

        years = sorted(
            {
                int(fact["fiscal_year"])
                for fact in facts
                if fact.get("fiscal_year") is not None
            },
            reverse=True,
        )[:years_cap]
        if not years:
            return None

        latest = dedupe_facts(facts, set(years))
        by_concept: dict[str, dict[int, dict]] = {}
        for (concept, year), fact in latest.items():
            by_concept.setdefault(concept, {})[year] = fact

        buckets: dict[str, list[FinancialsRow]] = {
            "balance_sheet": [],
            "income_statement": [],
            "cash_flow": [],
            "other": [],
        }
        for concept in sorted(by_concept):
            year_facts = by_concept[concept]
            unit = _concept_unit(year_facts)
            values = {
                year: (
                    abbreviate_number(year_facts[year].get("value"), unit)
                    if abbreviate
                    else format_fact_value(year_facts[year].get("value"), unit)
                )
                for year in years
                if year in year_facts
            }
            row = FinancialsRow(
                concept=concept,
                label=humanize_concept(concept),
                values=values,
                unit=unit,
            )
            buckets[classify_concept(concept)].append(row)
        for rows in buckets.values():
            rows.sort(key=lambda row: (row.label.lower(), row.concept))

        warnings: list[str] = []
        if len(facts) > FACTS_GUIDANCE_THRESHOLD:
            warnings.append(
                f"{len(facts):,} facts in this window (guidance: "
                f"{FACTS_GUIDANCE_THRESHOLD:,}); narrow the years or period "
                "for a lighter view."
            )

        return FinancialsView(
            ticker=ticker,
            company_name=self._company_name(ticker),
            fiscal_period=period,
            years=years,
            balance_sheet=buckets["balance_sheet"],
            income_statement=buckets["income_statement"],
            cash_flow=buckets["cash_flow"],
            other=buckets["other"],
            unmatched_count=len(buckets["other"]),
            extraction_warnings=warnings,
        )

    # ------------------------------------------------------------------
    def _company_name(self, ticker: str) -> str:
        getter = getattr(self._repo, "get_company_name", None)
        if getter is None:
            return ticker
        try:
            return getter(ticker) or ticker
        except Exception:  # noqa: BLE001 — the name is cosmetic
            return ticker

    def _demo_view(
        self, ticker: str, fiscal_period: str, max_years: int
    ) -> FinancialsView | None:
        """Offline fixtures (annual only): ``data/demo/financials/<T>.json``."""
        if fiscal_period != "FY":
            return None
        path = DEMO_ROOT / "financials" / f"{ticker}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        years = [int(year) for year in payload.get("years", [])][:max_years]
        other = _rows_from_payload(payload.get("other", []), years)
        return FinancialsView(
            ticker=str(payload.get("ticker") or ticker),
            company_name=str(payload.get("company_name") or ticker),
            fiscal_period="FY",
            years=years,
            balance_sheet=_rows_from_payload(payload.get("balance_sheet", []), years),
            income_statement=_rows_from_payload(
                payload.get("income_statement", []), years
            ),
            cash_flow=_rows_from_payload(payload.get("cash_flow", []), years),
            other=other,
            unmatched_count=int(payload.get("unmatched_count") or len(other)),
            extraction_warnings=([str(payload["note"])] if payload.get("note") else []),
        )
