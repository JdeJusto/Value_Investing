import streamlit as st
from backend.providers.yahoo import YahooFinanceProvider
from backend.providers.edgar import EdgarProvider
from backend.analytics.service import CompanyAnalysisService
from backend.services.screener_service import StockScreenerService
from backend.config.settings import get_sec_email, get_sec_name


@st.cache_resource
def get_market_provider():
    return YahooFinanceProvider()


@st.cache_resource
def get_providers():
    yahoo = get_market_provider()
    edgar = EdgarProvider(email=get_sec_email(), name=get_sec_name())
    return yahoo, edgar


@st.cache_resource
def get_analysis_service():
    yahoo, edgar = get_providers()
    return CompanyAnalysisService(
        financial_providers=[yahoo, edgar],
        market_provider=yahoo,
    )


@st.cache_resource
def get_screener_service():
    yahoo, edgar = get_providers()
    return StockScreenerService(
        financial_providers=[yahoo, edgar],
        market_provider=yahoo,
    )
