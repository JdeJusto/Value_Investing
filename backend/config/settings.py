import os
from dotenv import load_dotenv

load_dotenv()


def get_sec_email() -> str:
    return os.getenv("SEC_EMAIL", "jaimedejusto@gmail.com")


def get_sec_name() -> str:
    return os.getenv("SEC_NAME", "Jaime")


def get_output_dir() -> str:
    return os.getenv("OUTPUT_DIR", "outputs")


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/value_investing",
    )


DEFAULT_TAX_RATE = 0.21
DEFAULT_WACC = 0.08
DEFAULT_MARKET_RETURN = 0.10
DEFAULT_GROWTH_RATE = 0.05
DEFAULT_TERMINAL_GROWTH = 0.02
DCF_PROJECTION_YEARS = 5
