from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str | None = None
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    country: str | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    beta: float | None = None
    price: float | None = None
    currency: str | None = None

    model_config = {"from_attributes": True}


class CompanySearchResult(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    exchange: str | None = None


class MetricInterpretation(BaseModel):
    value: float | None = None
    formatted: str
    interpretation: str


class AnalysisResponse(BaseModel):
    ticker: str
    name: str | None = None
    price: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    score: float
    revenue: float | None = None
    net_income: float | None = None
    fcf: float | None = None
    metrics: dict[str, MetricInterpretation]


class FilterSchema(BaseModel):
    field: str
    operator: str
    value: Any | None = None


class ScreenerRequest(BaseModel):
    tickers: list[str] | None = None
    filters: list[FilterSchema] = []
    top_n: int = Field(default=25, ge=1, le=100)


class ScreenerJobResponse(BaseModel):
    job_id: str
    status: str


class ScreenerJobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    results: list[dict[str, Any]] | None = None
    error_message: str | None = None


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class PortfolioUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class PortfolioItemCreate(BaseModel):
    ticker: str
    shares: float = Field(ge=0)
    avg_cost: float | None = None
    added_date: str | None = None
    notes: str | None = None


class PortfolioItemUpdate(BaseModel):
    shares: float | None = Field(ge=0, default=None)
    avg_cost: float | None = None
    notes: str | None = None


class PortfolioResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_public: bool
    created_at: datetime
    updated_at: datetime
    ticker_count: int = 0
    items: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    ticker: str
    metric_name: str
    operator: str
    threshold: float
    notify_email: bool = True
    notify_push: bool = False


class AlertResponse(BaseModel):
    id: int
    ticker: str
    metric_name: str
    operator: str
    threshold: float
    is_active: bool
    notify_email: bool
    notify_push: bool
    last_triggered: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tickers: list[str] = []


class WatchlistResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    ticker_count: int = 0
    items: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}
