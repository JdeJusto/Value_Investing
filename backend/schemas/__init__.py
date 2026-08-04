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
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyResponse(BaseModel):
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    country: Optional[str] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    beta: Optional[float] = None
    price: Optional[float] = None
    currency: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanySearchResult(BaseModel):
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None


class MetricInterpretation(BaseModel):
    value: Optional[float] = None
    formatted: str
    interpretation: str


class AnalysisResponse(BaseModel):
    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    score: float
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    fcf: Optional[float] = None
    metrics: dict[str, MetricInterpretation]


class FilterSchema(BaseModel):
    field: str
    operator: str
    value: Optional[Any] = None


class ScreenerRequest(BaseModel):
    tickers: Optional[list[str]] = None
    filters: list[FilterSchema] = []
    top_n: int = Field(default=25, ge=1, le=100)


class ScreenerJobResponse(BaseModel):
    job_id: str
    status: str


class ScreenerJobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    results: Optional[list[dict[str, Any]]] = None
    error_message: Optional[str] = None


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class PortfolioItemCreate(BaseModel):
    ticker: str
    shares: float = Field(ge=0)
    avg_cost: Optional[float] = None
    added_date: Optional[str] = None
    notes: Optional[str] = None


class PortfolioItemUpdate(BaseModel):
    shares: Optional[float] = Field(ge=0, default=None)
    avg_cost: Optional[float] = None
    notes: Optional[str] = None


class PortfolioResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
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
    last_triggered: Optional[datetime] = None
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
