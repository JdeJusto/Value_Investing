import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production-abcdef123456")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/value_investing",
)
SQLALCHEMY_DATABASE_URI = os.getenv(
    "SQLALCHEMY_DATABASE_URI",
    DATABASE_URL,
)
SYNC_DATABASE_URL = os.getenv(
    "SYNC_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/value_investing",
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

SEC_EMAIL = os.getenv("SEC_EMAIL", "jaimedejusto@gmail.com")
SEC_NAME = os.getenv("SEC_NAME", "Jaime")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "outputs"))

DEFAULT_TAX_RATE = float(os.getenv("DEFAULT_TAX_RATE", "0.21"))
DEFAULT_WACC = float(os.getenv("DEFAULT_WACC", "0.08"))
DEFAULT_MARKET_RETURN = float(os.getenv("DEFAULT_MARKET_RETURN", "0.10"))
DEFAULT_GROWTH_RATE = float(os.getenv("DEFAULT_GROWTH_RATE", "0.05"))
DEFAULT_TERMINAL_GROWTH = float(os.getenv("DEFAULT_TERMINAL_GROWTH", "0.02"))
DCF_PROJECTION_YEARS = int(os.getenv("DCF_PROJECTION_YEARS", "5"))

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

FINANCIAL_CACHE_TTL = int(os.getenv("FINANCIAL_CACHE_TTL", "900"))
ANALYSIS_CACHE_TTL = int(os.getenv("ANALYSIS_CACHE_TTL", "3600"))
