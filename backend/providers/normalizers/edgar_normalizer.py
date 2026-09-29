"""Adapter: SEC EDGAR raw data → NormalizedFinancials."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
    RawFinancialsYear,
)
from backend.providers.normalizers.base import FinancialNormalizer
from backend.providers.normalizers.quality import apply_quality_metrics


class EdgarNormalizer(FinancialNormalizer):
    """Normalizes statements returned by ``EdgarProvider``.

    EDGAR exposes fewer standardized concepts than Yahoo; missing fields
    stay ``None`` and are filled by other providers on later loads or left
    absent for metrics that cannot be computed. Key metrics such as free
    cash flow are derived from available inputs whenever possible.
    """

    @property
    def source(self) -> ProviderName:
        return ProviderName.EDGAR

    def normalize(self, raw: RawFinancialsYear) -> NormalizedFinancials | None:
        income, balance, cash_flow = raw.income, raw.balance, raw.cash_flow
        if income is None and balance is None and cash_flow is None:
            return None

        ebit = income.ebit if income else None
        operating_cash_flow = cash_flow.operating_cash_flow if cash_flow else None
        capital_expenditure = cash_flow.capital_expenditure if cash_flow else None

        derived_metrics: list[str] = []
        free_cash_flow = cash_flow.free_cash_flow if cash_flow else None
        if (
            free_cash_flow is None
            and operating_cash_flow is not None
            and capital_expenditure is not None
        ):
            free_cash_flow = operating_cash_flow - capital_expenditure
            derived_metrics.append("free_cash_flow")

        financials = NormalizedFinancials(
            ticker=raw.ticker,
            fiscal_year=raw.year,
            revenue=income.revenue if income else None,
            operating_income=ebit,
            ebit=ebit,
            net_income=income.net_income if income else None,
            total_assets=balance.total_assets if balance else None,
            total_liabilities=balance.total_liabilities if balance else None,
            total_debt=balance.total_debt if balance else None,
            stockholders_equity=balance.stockholders_equity if balance else None,
            operating_cash_flow=operating_cash_flow,
            capital_expenditure=capital_expenditure,
            free_cash_flow=free_cash_flow,
            shares_outstanding=(
                int(raw.shares_outstanding) if raw.shares_outstanding else None
            ),
            source=self.source,
            loaded_at=datetime.now(UTC),
            derived_metrics=derived_metrics,
        )
        return apply_quality_metrics(financials)
