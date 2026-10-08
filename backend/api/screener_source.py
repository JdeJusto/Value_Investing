"""Screener data source for the API: universe -> enriched rows.

The expensive half of ``GET /api/v1/screener`` (Yahoo snapshot prefetch +
per-ticker methodologies over a whole index) lives here, split from the
route so the route can cache, filter and paginate the result and tests can
stub the pipeline through :func:`backend.api.deps.get_screener_source`.

Reuses the exact same services as the CLI/Streamlit screener:
``StockScreenerService.screen`` (prices + ratios + composite score) and
``ui_adapter.enrich_rows`` (verdict/score/category per methodology), with
``buffett_classic`` as the default methodology.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.api.responses import ApiError
from backend.services.ui_adapter import parse_universe_tickers

UNIVERSE_PATH = Path("config/universe.csv")

#: Named subsets accepted by ``?universe=`` (mirrors scripts/daily_workflow).
NAMED_UNIVERSES: dict[str, frozenset[str]] = {
    "sp500": frozenset({"SP500"}),
    "nasdaq100": frozenset({"NASDAQ100"}),
    "russell2000": frozenset({"RUSSELL2000"}),
    "european": frozenset(
        {
            "FTSE100",
            "DAX40",
            "CAC40",
            "IBEX35",
            "FTSE_MIB",
            "AEX",
            "SMI",
            "OMXS30",
            "OMXC25",
        }
    ),
}

DEFAULT_METHODOLOGY = "buffett_classic"

#: The screener reads the newest N fiscal years, matching the Streamlit page.
SCREENER_HISTORY_YEARS = 10


def canonical_universe(universe: str) -> tuple[str, set[str]]:
    """Normalize ``?universe=`` into (echo label, lowercase tokens).

    Raises :class:`ApiError` 400 ``INVALID_UNIVERSE`` for unknown tokens.
    """
    tokens = {token.strip().lower() for token in (universe or "").split(",")}
    tokens.discard("")
    if not tokens:
        raise ApiError(400, "INVALID_UNIVERSE", "universe must not be empty")
    invalid = tokens - set(NAMED_UNIVERSES) - {"all"}
    if invalid:
        raise ApiError(
            400,
            "INVALID_UNIVERSE",
            "Unknown universe token(s): "
            f"{', '.join(sorted(invalid))}. Valid: "
            f"{', '.join(sorted(NAMED_UNIVERSES))}, all.",
        )
    return ",".join(sorted(tokens)), tokens


def resolve_universe_tickers(tokens: set[str], path: Path = UNIVERSE_PATH) -> list[str]:
    """Tickers for the selected universe tokens from the master CSV.

    Raises :class:`ApiError` 503 ``SERVICE_UNAVAILABLE`` when the master file
    is missing and 400 ``INVALID_UNIVERSE`` when it holds no matching row.
    """
    if not path.exists():
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            f"Universe file not found: {path}",
        )
    csv_text = path.read_text(encoding="utf-8")
    if "all" in tokens:
        selected = ["ALL"]
    else:
        sources: set[str] = set()
        for token in tokens:
            sources |= NAMED_UNIVERSES[token]
        selected = sorted(sources)
    tickers = parse_universe_tickers(csv_text, selected)
    if not tickers:
        raise ApiError(
            400,
            "INVALID_UNIVERSE",
            f"No ticker matches universe: {','.join(sorted(tokens))}",
        )
    return tickers


def load_enriched_universe(tickers: list[str], repository: Any) -> list[dict]:
    """Screen ``tickers`` and enrich with verdict/score/category.

    This is the expensive call the route caches (Yahoo snapshot prefetch +
    per-ticker analytics + methodologies). Rows are the internal shape the
    route filters on: ``per``/``roe``/``fcf_yield``/``market_cap`` keep the
    screener's units so ``ui_adapter.apply_numeric_filters`` applies as-is.
    """
    from backend.app.cli import build_data_pipeline
    from backend.providers.yahoo import YahooFinanceProvider
    from backend.services.consensus_service import normalize_lynch_category
    from backend.services.screener_service import StockScreenerService
    from backend.services.ui_adapter import enrich_rows, run_methodologies

    service = StockScreenerService(
        repository=repository,
        market_provider=YahooFinanceProvider(),
        loader=build_data_pipeline(),
    )
    screened = service.screen(tickers=list(tickers), top_n=len(tickers))

    row_dicts = [
        {
            "ticker": row.ticker,
            "name": row.name,
            "price": row.price,
            "market_cap": row.market_cap,
            "per": row.per,
            "roe": row.roe,
            "fcf_yield": row.fcf_yield,
        }
        for row in screened
    ]
    sectors = _sector_map(repository, [row.ticker for row in screened])

    def load_fundamentals(ticker: str) -> list:
        rows = repository.get_best_available(ticker, max_years=SCREENER_HISTORY_YEARS)
        return [row for row in (rows or []) if row is not None]

    enriched = enrich_rows(
        row_dicts, DEFAULT_METHODOLOGY, sectors, load_fundamentals, run_methodologies
    )
    by_ticker = {row.ticker: row for row in screened}
    rows: list[dict] = []
    for item in enriched:
        base = by_ticker.get(item["Ticker"])
        rows.append(
            {
                "ticker": item["Ticker"],
                "name": item["Name"],
                "sector": item["Sector"],
                "price": item["Price"],
                "market_cap": base.market_cap if base is not None else None,
                "per": item["P/E"],
                "roe": item["ROE"],
                "fcf_yield": item["FCF Yield"],
                "verdict": item["Verdict"],
                "score": item["Score"],
                "category": normalize_lynch_category(
                    str(item["Category"] or "UNKNOWN")
                ),
                "key_reason": item["Key Reason"],
            }
        )
    rows.sort(
        key=lambda row: (row["score"] is None, -(row["score"] or 0.0), row["ticker"])
    )
    return rows


def _sector_map(repository: Any, tickers: list[str]) -> dict[str, str | None]:
    """Sector per ticker in one repository read (best effort)."""
    getter = getattr(repository, "get_sector_map", None)
    if getter is None:
        return {}
    try:
        return dict(getter(tickers))
    except Exception:  # noqa: BLE001 — a missing sector must not fail the screen
        return {}
