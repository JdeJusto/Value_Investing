import streamlit as st

from backend.analytics.service import CompanyAnalysisService
from backend.app.cli import build_data_pipeline, build_financial_repository
from backend.providers.yahoo import YahooFinanceProvider
from backend.services.screener_service import StockScreenerService


@st.cache_resource
def get_market_provider():
    return YahooFinanceProvider()


@st.cache_resource
def get_analysis_service():
    return CompanyAnalysisService(
        repository=build_financial_repository(),
        market_provider=get_market_provider(),
        loader=build_data_pipeline(),
    )


@st.cache_resource
def get_screener_service():
    return StockScreenerService(
        repository=build_financial_repository(),
        market_provider=get_market_provider(),
        loader=build_data_pipeline(),
    )
