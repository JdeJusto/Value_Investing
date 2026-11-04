"""Effective-year selection: latest complete balance (Assets + Equity).

Financial-DataBase's ``core_financials`` may hold a newer fiscal year whose
latest ``period_end`` has Assets + Liabilities but no Equity (MRX FY2025).
Analysis must back off to the previous complete year instead of anchoring on
an incomplete balance.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.analytics.service import CompanyAnalysisService, effective_year
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)


def _row(
    year: int,
    *,
    revenue: float | None = 100.0,
    total_assets: float | None = 1_000.0,
    total_liabilities: float | None = 900.0,
    stockholders_equity: float | None = 100.0,
) -> NormalizedFinancials:
    return NormalizedFinancials(
        ticker="TEST",
        fiscal_year=year,
        source=ProviderName.EDGAR,
        revenue=revenue,
        net_income=10.0,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        stockholders_equity=stockholders_equity,
        loaded_at=datetime.now(UTC),
    )


class _Repo:
    """Minimal repository exposing only the effective-year contract."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = 0

    def get_best_available(self, ticker: str):
        self.calls += 1
        return list(self.rows)


class _RepoWithEffectiveYear(_Repo):
    def __init__(self, rows, year=None):
        super().__init__(rows)
        self.year = year

    def get_effective_year(self, ticker: str) -> int | None:
        return self.year


class _HistoryRepo:
    """History source only: forces the row-based effective-year fallback."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = 0

    def get_best_available(self, ticker: str):
        self.calls += 1
        return list(self.rows)


def test_effective_year_prefers_the_repository_value():
    repo = _RepoWithEffectiveYear([], year=2024)

    assert effective_year("MRX", repo) == 2024
    assert repo.calls == 0


def test_effective_year_falls_back_to_the_latest_complete_row():
    repo = _Repo([_row(2025, stockholders_equity=None), _row(2024)])

    assert effective_year("MRX", repo) == 2024


def test_effective_year_returns_none_when_no_row_has_a_balance():
    repo = _Repo(
        [
            _row(2025, total_assets=None, total_liabilities=None),
            _row(2024, total_assets=None, total_liabilities=None),
        ]
    )

    assert effective_year("TEST", repo) is None


def test_load_history_drops_a_newer_incomplete_balance():
    """MRX FY2025 (no equity) must not anchor the analysis over FY2024."""
    repo = _HistoryRepo(
        [
            _row(2025, stockholders_equity=None),
            _row(2024, revenue=90.0),
        ]
    )
    service = CompanyAnalysisService(repository=repo, market_provider=None)

    history = service._load_history("MRX")

    assert [row.fiscal_year for row in history] == [2024]


def test_load_history_keeps_a_complete_latest_year():
    repo = _HistoryRepo([_row(2025), _row(2024)])
    service = CompanyAnalysisService(repository=repo, market_provider=None)

    history = service._load_history("AAPL")

    assert [row.fiscal_year for row in history] == [2025, 2024]


def test_load_history_without_any_balance_does_not_raise():
    repo = _HistoryRepo(
        [
            _row(2025, total_assets=None, total_liabilities=None),
            _row(2024, total_assets=None, total_liabilities=None),
        ]
    )
    service = CompanyAnalysisService(repository=repo, market_provider=None)

    history = service._load_history("TEST")

    assert [row.fiscal_year for row in history] == [2025, 2024]
