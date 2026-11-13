"""Test-suite defaults.

PriceService reads its pacing/cache switches at import time. Tests must not
sleep between mocked yfinance calls or write into the repository cache, so
the defaults are relaxed here before any test module imports the service.
"""

import os

os.environ.setdefault("PRICE_MIN_INTERVAL", "0")
os.environ.setdefault("PRICE_DISK_CACHE", "0")
os.environ.setdefault("PRICE_YF_VERBOSE", "0")

import pytest


@pytest.fixture(autouse=True)
def _isolate_price_provider_env(monkeypatch):
    """Never let a developer's local .env change test behavior.

    ``backend.app.cli`` calls ``load_dotenv()`` at import time, so a local
    ``PRICE_PROVIDER``/FMP/Tiingo key would otherwise leak into the Yahoo
    tests. Provider tests set these variables explicitly inside the test.
    """
    for variable in ("PRICE_PROVIDER", "FMP_API_KEY", "TIINGO_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
