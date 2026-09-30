class FinancialRepository:
    def __init__(self, provider):
        self._provider = provider

    def get_revenue(self, ticker: str, year_index: int = 0) -> float | None:
        return self._provider.get_revenue(ticker, year_index)

    def get_ebit(self, ticker: str, year_index: int = 0) -> float | None:
        return self._provider.get_ebit(ticker, year_index)

    def get_net_income(self, ticker: str, year_index: int = 0) -> float | None:
        return self._provider.get_net_income(ticker, year_index)

    def get_free_cash_flow(self, ticker: str, year_index: int = 0) -> float | None:
        return self._provider.get_free_cash_flow(ticker, year_index)
