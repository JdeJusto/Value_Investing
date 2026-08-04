from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.auth import router as auth_router
from backend.api.v1.companies import router as companies_router
from backend.api.v1.screener import router as screener_router
from backend.api.v1.portfolios import router as portfolios_router
from backend.api.v1.alerts import router as alerts_router
from backend.api.v1.watchlists import router as watchlists_router
from backend.core.config import CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ValueInvest Pro",
    description="Plataforma de análisis fundamental para inversores value",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")
app.include_router(screener_router, prefix="/api/v1")
app.include_router(portfolios_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(watchlists_router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}
