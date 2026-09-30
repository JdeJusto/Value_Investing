"""Shared CLI preflight: fail fast on tickers unknown to Financial-DataBase."""

from __future__ import annotations


def require_known_tickers(tickers: list[str]) -> None:
    """Print a clear error and exit 2 when a ticker has no active FDB listing.

    A database failure degrades (the analysis proceeds) instead of blocking
    on infrastructure trouble. The message is shared by every analyze
    command so they all fail the same way.
    """
    from backend.services.ticker_resolver import resolve_ticker
    from cli.formatters import red

    unknown: list[str] = []
    for ticker in tickers:
        try:
            resolved = resolve_ticker(ticker)
        except Exception:  # noqa: BLE001 — DB unreachable: do not block
            return
        if resolved is None:
            unknown.append(ticker)
    if not unknown:
        return
    for ticker in unknown:
        print(red(f"Error: ticker '{ticker}' not found in Financial-DataBase."))
    print(
        "Check that it is a valid listed ticker or run "
        "`python -m scripts.daily_workflow --refresh` to update the universe."
    )
    raise SystemExit(2)
