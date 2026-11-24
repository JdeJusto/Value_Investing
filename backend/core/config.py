"""Shared valuation defaults used by the analytics services.

Environment-specific connection settings (database URL, SEC contact, output
directory) live in :mod:`backend.config.settings`; this module only holds the
deterministic DCF defaults that the CLI and the Streamlit UI share. The values
can still be overridden through the environment, as documented in
``.env.example``.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_TAX_RATE = float(os.getenv("DEFAULT_TAX_RATE", "0.21"))
DEFAULT_WACC = float(os.getenv("DEFAULT_WACC", "0.08"))
DEFAULT_MARKET_RETURN = float(os.getenv("DEFAULT_MARKET_RETURN", "0.10"))
DEFAULT_GROWTH_RATE = float(os.getenv("DEFAULT_GROWTH_RATE", "0.05"))
DEFAULT_TERMINAL_GROWTH = float(os.getenv("DEFAULT_TERMINAL_GROWTH", "0.02"))
DCF_PROJECTION_YEARS = int(os.getenv("DCF_PROJECTION_YEARS", "5"))
