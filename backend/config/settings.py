import os

from dotenv import load_dotenv

load_dotenv()


def get_sec_email() -> str:
    """SEC contact e-mail, read from the environment only.

    The SEC requires a declared contact and the value is personal, so it
    lives in the git-ignored ``.env`` (``SEC_EMAIL=...``) and is never
    hardcoded. Failing fast with a clear message beats sending a request
    that the SEC answers with 403, or worse, attributing it to someone
    else.
    """
    email = os.getenv("SEC_EMAIL", "").strip()
    if not email:
        raise RuntimeError(
            "SEC_EMAIL is not configured. Set it in .env to a real contact "
            "address, e.g. SEC_EMAIL=you@your-domain.com (copy "
            ".env.example). The SEC rejects requests without a declared "
            "contact; never a github.com address (HTTP 403, see "
            "Financial-DataBase docs/sec_403_investigation.md)."
        )
    return email


def get_sec_name() -> str:
    return os.getenv("SEC_NAME", "Jaime")


def get_output_dir() -> str:
    return os.getenv("OUTPUT_DIR", "outputs")


def get_database_url(sync: bool = False) -> str:
    if sync:
        return os.getenv(
            "SYNC_DATABASE_URL",
            "postgresql+psycopg2://postgres:postgres@localhost:5432/value_investing",
        )
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/value_investing",
    )


DEFAULT_TAX_RATE = 0.21
DEFAULT_WACC = 0.08
DEFAULT_MARKET_RETURN = 0.10
DEFAULT_GROWTH_RATE = 0.05
DEFAULT_TERMINAL_GROWTH = 0.02
DCF_PROJECTION_YEARS = 5
