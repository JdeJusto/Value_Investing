"""Fact normalization, record building and writes.

Mixin for :class:`FinancialDatabaseRepository` (pure move).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.domain.value_objects.financials_normalized import (
    ANNUAL_PERIOD,
    NormalizedFinancials,
    ProviderName,
)
from backend.repositories.fdb_concept_mapping import (
    _COMMON_ONLY_DIVIDEND_CONCEPTS,
    BALANCE_SHEET_CONCEPTS,
    CASH_FLOW_CONCEPT_RANK,
    CASH_FLOW_CONCEPTS,
    DEBT_CURRENT_RANK,
    DEBT_NONCURRENT_RANK,
    INCOME_CONCEPT_RANK,
    INCOME_STATEMENT_CONCEPTS,
    _income_convention,
)


class NormalizationMixin:
    def _normalize_financial_facts(
        self, facts: list[dict], bucket_year: int | None = None
    ) -> dict:
        """Normalize a list of financial facts into financial statement components.

        Args:
            facts: List of financial fact dictionaries from database
            bucket_year: Fiscal year this facts list is supposed to represent.
                When given, rows whose ``period_end`` falls outside that
                calendar year are dropped so the newest-period_end dedup cannot
                pick a value from a neighbouring year (see below).

        Returns:
            Dictionary with financial statement data organized by statement type
        """
        # Initialize statement containers
        income_data = {}
        balance_data = {}
        cash_flow_data = {}
        dividends_paid_concept: str | None = None

        # A fiscal-year bucket can hold facts from other years: the latest 10-K
        # embeds its comparatives, and a sync may tag the SAME filing under two
        # different fiscal_years (e.g. a Jan-31 fiscal-year-end company whose
        # 10-K was ingested as both FY2025 and FY2026). Each bucket is only
        # responsible for the rows whose period_end falls within the labelled
        # year; dropping the rest keeps a next-year value from winning the
        # newest-period_end dedup and keeps as-of-date cover-page facts (like
        # EntityCommonStockSharesOutstanding) out of the balance snapshot. That
        # filter runs in the single precompute pass below (same walk that
        # builds the sort keys, so each fact parses its dates only once).

        # A fiscal-year bucket stores the latest 10-K plus its comparative
        # years (each fact carries its own period_start/period_end), and some
        # elements are reported both quarterly and year-to-date with the same
        # period_end. Order candidates so the true annual figure wins:
        #   1. longest period span (the ANNUAL fact; 10-K supplemental
        #      quarterly tables are re-tagged 'FY' by SEC, so a quarter can
        #      carry a LATER period_end than the real annual figure — e.g.
        #      Salesforce's Jan-31 fiscal year),
        #   2. newest period_end (the target comparative year),
        #   3. preferred concept for the field (e.g. 'Revenues' over
        #      RevenueFromContractWithCustomerExcludingAssessedTax),
        #   4. earliest period_start (longest cumulative duration).
        def _date_ord(value):
            if value is None:
                return 0
            if isinstance(value, date):
                return value.toordinal()
            try:
                return date.fromisoformat(str(value)[:10]).toordinal()
            except (ValueError, TypeError):
                return 0

        # Precompute each fact's sort key ONCE, before sorting. The previous
        # implementation re-parsed the two ISO dates inside every comparison
        # of sorted() (and re-parsed period_end again in the bucket filter),
        # which dominated the CPU time of large fact buckets. Each row now
        # parses period_end/period_start a single time.
        keyed = []
        for f in facts:
            pe = f.get("period_end")
            ps = f.get("period_start")
            pe_ord = _date_ord(pe)
            ps_ord = _date_ord(ps)
            concept = f.get("concept") or ""
            key = (
                pe_ord - ps_ord if pe is not None and ps is not None else 0,
                pe_ord,
                -INCOME_CONCEPT_RANK.get(
                    concept, CASH_FLOW_CONCEPT_RANK.get(concept, 10**9)
                ),
                -ps_ord,
            )
            year = date.fromordinal(pe_ord).year if pe_ord else None
            keyed.append(((key, year), f))

        if bucket_year is not None:
            year_rows = [f for ((_key, year), f) in keyed if year == bucket_year]
            if year_rows:
                keyed = [entry for entry in keyed if entry[0][1] == bucket_year]

        keyed.sort(key=lambda entry: entry[0][0], reverse=True)
        facts = [f for _, f in keyed]
        # The newest balance-sheet comparative drives total-debt aggregation.
        # Cover-page / as-of facts (e.g. EntityCommonStockSharesOutstanding,
        # which post-dates the fiscal year end) are not part of the balance
        # snapshot and must not lift MAX(): doing so would drop every balance
        # line, leaving total debt empty.
        max_pe = next(
            (
                f.get("period_end")
                for f in facts
                if f.get("period_end") is not None
                and f.get("concept") in BALANCE_SHEET_CONCEPTS
            ),
            None,
        )

        # Banks/brokers present a net-of-interest top line. Capture their
        # interest + non-interest income so their revenue can be reconstructed
        # when no net-revenue tag is filed.
        bank_interest = None
        bank_noninterest = None
        # REIT rental income (see the value-based override below).
        rental_income = None
        # R&D filed under the ExcludingAcquiredInProcessCost tag (JNJ keeps
        # its substantive line here; see the dominance override at the end).
        rnd_excluding = None
        # Best current / non-current debt figure within the newest comparative
        # (concept-priority single pick per portion, see DEBT_*_PRIORITY).
        debt_current = None
        debt_noncurrent = None

        # Process each fact
        for fact in facts:
            concept = fact["concept"]
            value = float(fact["value"]) if fact["value"] is not None else None

            # Skip if no value
            if value is None:
                continue

            # Map to income statement
            if concept in INCOME_STATEMENT_CONCEPTS:
                field_name = INCOME_STATEMENT_CONCEPTS[concept]
                if concept == "OperatingLeaseLeaseIncome" and rental_income is None:
                    rental_income = value
                if (
                    field_name == "research_development"
                    and concept
                    == "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"
                    and rnd_excluding is None
                ):
                    rnd_excluding = value
                # Handle duplicates by taking the first fact ordered above
                if field_name not in income_data or income_data[field_name] is None:
                    income_data[field_name] = value
                    if field_name == "net_income":
                        income_data["net_income_convention"] = _income_convention(
                            concept
                        )

            # Map to balance sheet
            elif (
                concept in BALANCE_SHEET_CONCEPTS
                or concept in DEBT_CURRENT_RANK
                or concept in DEBT_NONCURRENT_RANK
            ):
                field_name = BALANCE_SHEET_CONCEPTS.get(concept, "total_debt")
                # Total debt: take the current and non-current portions from the
                # SAME (newest) comparative, preferring one tag per portion so
                # equivalent aliases are not double counted.
                if (
                    field_name == "total_debt"
                    and max_pe is not None
                    and fact.get("period_end") != max_pe
                ):
                    continue
                if field_name == "total_debt":
                    cur_rank = DEBT_CURRENT_RANK.get(concept)
                    noncur_rank = DEBT_NONCURRENT_RANK.get(concept)
                    if cur_rank is not None and (
                        debt_current is None or cur_rank < debt_current[1]
                    ):
                        debt_current = (value, cur_rank)
                    elif noncur_rank is not None and (
                        debt_noncurrent is None or noncur_rank < debt_noncurrent[1]
                    ):
                        debt_noncurrent = (value, noncur_rank)
                else:
                    # Handle duplicates by taking the newest-comparative value
                    if (
                        field_name not in balance_data
                        or balance_data[field_name] is None
                    ):
                        balance_data[field_name] = value

            # Map to cash flow
            elif concept in CASH_FLOW_CONCEPTS:
                field_name = CASH_FLOW_CONCEPTS[concept]
                # Handle capital expenditure (make positive)
                if field_name == "capital_expenditure" and value is not None:
                    value = abs(value)  # Ensure positive

                # Handle duplicates by taking the newest-comparative value
                if (
                    field_name not in cash_flow_data
                    or cash_flow_data[field_name] is None
                ):
                    cash_flow_data[field_name] = value
                    if field_name == "dividends_paid":
                        dividends_paid_concept = concept

            # Track bank top-line components (not part of the standard mapping)
            elif concept == "InterestIncomeExpenseNet" and bank_interest is None:
                bank_interest = value
            elif concept == "NoninterestIncome" and bank_noninterest is None:
                bank_noninterest = value
            elif concept == "OperatingLeaseLeaseIncome" and rental_income is None:
                rental_income = value

        # Combine the current + non-current debt portions (single preferred tag
        # each) into total_debt. Absent both, the field stays unset.
        if debt_current is not None or debt_noncurrent is not None:
            balance_data["total_debt"] = (debt_current[0] if debt_current else 0.0) + (
                debt_noncurrent[0] if debt_noncurrent else 0.0
            )

        # Most filers present operating income (OperatingIncomeLoss) with no
        # separate EBIT tag; treat the two as equivalent so the EBIT-based
        # multiples (EV/EBIT, ROIC) keep working when only operating income is
        # filed.
        if (
            income_data.get("ebit") is None
            and income_data.get("operating_income") is not None
        ):
            income_data["ebit"] = income_data["operating_income"]

        # Gross profit = revenue - cost of revenue is the standard US-GAAP
        # identity, used when a filer does not tag GrossProfit directly. GM
        # last filed the tag in FY2012 and T stopped after the 2023 restatement,
        # but their cost lines (CostOfGoodsAndServicesSold / CostOfRevenue)
        # remain tagged for earlier years, so the margin series is kept instead
        # of dropped. Never overrides a filed figure (fires only when absent).
        if (
            income_data.get("gross_profit") is None
            and income_data.get("revenue") is not None
            and income_data.get("cogs") is not None
        ):
            income_data["gross_profit"] = income_data["revenue"] - income_data["cogs"]

        # REITs whose rental income is the whole top line (no revenue tag filed,
        # or only a small contract-revenue tag) report it as OperatingLease
        # LeaseIncome. Prefer the rental figure when it dominates whatever
        # contract-revenue tag was picked (e.g. CPT's 1.57B rental vs a 13M
        # contract tag) while leaving e.g. DD (6.85B sales vs 74M rental)
        # untouched. A non-positive rental figure never replaces a real top
        # line.
        if (
            rental_income is not None
            and rental_income > 0
            and (
                income_data.get("revenue") is None
                or rental_income > income_data["revenue"]
            )
        ):
            income_data["revenue"] = rental_income

        # Banks/brokers report a net-of-interest top line. When both
        # components exist, reconstruct revenue as their sum — but only when
        # the pair *dominates* whatever revenue tag was picked (mirrors the
        # REIT rule). A filer that reports a genuine, larger net-revenue tag
        # (some financial holding companies file `Revenues`) must never have
        # it clobbered by a smaller or non-positive reconstructed total; a
        # small incidental interest+non-interest pair must not shadow a
        # manufacturer's real sales either (e.g. 7M pair vs 1,000M Revenues).
        if bank_interest is not None and bank_noninterest is not None:
            bank_total = bank_interest + bank_noninterest
            current_rev = income_data.get("revenue")
            if bank_total > 0 and (current_rev is None or bank_total > current_rev):
                income_data["revenue"] = bank_total

        # JNJ's substantive R&D line lives under the ExcludingAcquiredInProcessCost
        # tag while its plain ResearchAndDevelopmentExpense tag only holds a
        # residual; other filers (AAPL, MSFT) report the plain tag only. When
        # both tags are present in the bucket keep the more complete (larger)
        # figure so a residual tag cannot read as 'no/low R&D'. Mirrors the
        # REIT/bank dominance overrides above.
        if rnd_excluding is not None and (
            income_data.get("research_development") is None
            or rnd_excluding > income_data["research_development"]
        ):
            income_data["research_development"] = rnd_excluding

        # A common-only cash dividend tag already excludes preferred
        # dividends; subtracting the income-statement preferred figure again
        # would double-count it (WFC/USB file PaymentsOfDividendsCommonStock
        # plus a preferred tag). Only keep it when the total tag won.
        if dividends_paid_concept in _COMMON_ONLY_DIVIDEND_CONCEPTS:
            income_data["preferred_dividends"] = None

        return {
            "income": income_data,
            "balance": balance_data,
            "cash_flow": cash_flow_data,
        }

    def _calculate_derived_fields(self, statements: dict) -> dict:
        """Calculate derived fields like working capital and free cash flow.

        Args:
            statements: Dictionary with income, balance, cash_flow data

        Returns:
            Updated statements dictionary with derived fields calculated
        """
        cash_flow = statements["cash_flow"]

        # Calculate working capital: Current Assets - Current Liabilities
        # Since we don't have current assets/liabilities directly,
        # we'll approximate or skip for now
        # TODO: Add proper current assets/liabilities concept mapping

        # Calculate free cash flow: Operating Cash Flow - Capital Expenditure
        if (
            cash_flow.get("operating_cash_flow") is not None
            and cash_flow.get("capital_expenditure") is not None
        ):
            cash_flow["free_cash_flow"] = (
                cash_flow["operating_cash_flow"] - cash_flow["capital_expenditure"]
            )

        return statements

    def _build_normalized_financials(
        self,
        ticker: str,
        fiscal_year: int,
        statements: dict,
        loaded_at: datetime | None = None,
        split_adjustment_factor: float = 1.0,
        sector: str | None = None,
    ) -> NormalizedFinancials:
        """Build a NormalizedFinancials object from statement data.

        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year
            statements: Dictionary with income, balance, cash_flow data
            loaded_at: When this data was loaded (defaults to now)
            split_adjustment_factor: Multiplier restating this year's
                as-reported shares on today's post-split basis (see
                ``_cumulative_split_multiplier``); 1.0 when unknown.
            sector: Company sector label from ``companies.sector`` (None when
                the metadata layer does not supply one).

        Returns:
            NormalizedFinancials object
        """
        if loaded_at is None:
            loaded_at = datetime.now(UTC)

        income = statements["income"]
        balance = statements["balance"]
        cash_flow = statements["cash_flow"]

        # The statement dataclasses (IncomeStatement/BalanceSheet/
        # CashFlowStatement) are intentionally not materialized here: the
        # NormalizedFinancials value object below carries every field the
        # analysis layer reads, and the intermediate objects were never used.
        return NormalizedFinancials(
            ticker=ticker,
            fiscal_year=fiscal_year,
            # Income statement
            revenue=income.get("revenue"),
            cogs=income.get("cogs"),
            gross_profit=income.get("gross_profit"),
            operating_income=income.get("operating_income"),
            ebit=income.get("ebit"),
            ebitda=income.get("ebitda"),
            net_income=income.get("net_income"),
            net_income_convention=income.get("net_income_convention"),
            interest_expense=income.get("interest_expense"),
            tax_provision=income.get("tax_provision"),
            pretax_income=income.get("pretax_income"),
            # Balance sheet
            total_assets=balance.get("total_assets"),
            total_liabilities=balance.get("total_liabilities"),
            total_debt=balance.get("total_debt"),
            cash_and_equivalents=balance.get("cash_and_equivalents"),
            net_ppe=balance.get("net_ppe"),
            retained_earnings=balance.get("retained_earnings"),
            stockholders_equity=balance.get("stockholders_equity"),
            current_assets=balance.get("current_assets"),
            current_liabilities=balance.get("current_liabilities"),
            # working_capital is not a stored XBRL concept; derive it from the
            # balance-sheet split so liquidity ratios (and the Graham current
            # ratio) work without a separate lookup.
            working_capital=(
                balance.get("current_assets") - balance.get("current_liabilities")
                if balance.get("current_assets") is not None
                and balance.get("current_liabilities") is not None
                else balance.get("working_capital")
            ),
            # Cash flow
            operating_cash_flow=cash_flow.get("operating_cash_flow"),
            capital_expenditure=cash_flow.get("capital_expenditure"),
            free_cash_flow=cash_flow.get("free_cash_flow"),
            depreciation_amortization=cash_flow.get("depreciation_amortization"),
            dividends_paid=cash_flow.get("dividends_paid"),
            repurchase_of_stock=cash_flow.get("repurchase_of_stock"),
            working_capital_change=cash_flow.get("working_capital_change"),
            # Additional income statement fields. These were historically dropped from
            # the snapshot because they only lived on an intermediate
            # IncomeStatement object that no caller consumed; carrying them
            # straight into the NormalizedFinancials makes e.g. R&D spent
            # visible to analytics and methodologies.
            operating_expense=income.get("operating_expense"),
            research_development=income.get("research_development"),
            sga=income.get("sga"),
            non_operating_income_expense=income.get("non_operating_income_expense"),
            preferred_dividends=income.get("preferred_dividends"),
            # Context
            shares_outstanding=balance.get("shares_outstanding"),
            split_adjustment_factor=split_adjustment_factor,
            sector=sector,
            period=ANNUAL_PERIOD,
            currency="USD",  # TODO: Get from actual unit/currency data
            source=ProviderName.EDGAR,  # Financial-DataBase primarily has SEC data
            loaded_at=loaded_at,
            # Data quality (we don't have this info directly, so use defaults)
            data_completeness=None,
            data_quality_score=None,
            is_complete=False,
            data_source_priority=1,  # SEC EDGAR is high quality
            derived_metrics=[],
        )

    def upsert(self, financials: NormalizedFinancials) -> None:
        """Insert or update a single fiscal-year record.

        Note: This implementation is read-only for Financial-DataBase
        since we're primarily using it as a source of truth.
        For a full bidirectional sync, this would write to the database.
        """
        # Even though this is read-only, invalidate the ticker's cached
        # fundamentals so a future writer never serves stale data.
        self.invalidate_list_cache(financials.ticker.upper())

    def upsert_many(self, financials: list[NormalizedFinancials]) -> None:
        """Insert or update a batch of fiscal-year records in one operation."""
        # Read-only implementation; still invalidate the touched tickers.
        for row in financials:
            self.invalidate_list_cache(row.ticker.upper())

    def delete_ticker(self, ticker: str) -> None:
        """Remove all records for a ticker.

        Read-only implementation - no-op for Financial-DataBase
        since we treat it as a source of truth.
        """
