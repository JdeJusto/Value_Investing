"""Test-suite defaults.

PriceService reads its pacing/cache switches at import time. Tests must not
sleep between mocked yfinance calls or write into the repository cache, so
the defaults are relaxed here before any test module imports the service.
"""

import os

os.environ.setdefault("PRICE_MIN_INTERVAL", "0")
os.environ.setdefault("PRICE_DISK_CACHE", "0")
os.environ.setdefault("PRICE_YF_VERBOSE", "0")
