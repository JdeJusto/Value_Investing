"""Build the deterministic demo consensus fixture (30 companies).

The 8 demo tickers carry hand-picked verdicts; the 22 extra companies get a
rotating pattern so the page always shows every lens (top, per Lynch
category, disagreement zone). Deterministic: rerunning the script produces
the same file. Usage::

    python -m scripts.build_demo_consensus
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.compute_consensus_rankings import METHODOLOGY_KEYS

OUTPUT = Path("data/demo/consensus/consensus_demo.json")

#: The 8 demo tickers: (name, verdicts in METHODOLOGY_KEYS order, category).
DEMO_COMPANIES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "AAPL": (
        "Apple Inc.",
        ("BUY", "BUY", "WATCH", "BUY", "BUY", "HOLD", "BUY", "AVOID"),
        "STALWART",
    ),
    "MSFT": (
        "Microsoft Corporation",
        ("BUY", "BUY", "BUY", "AVOID", "BUY", "HOLD", "HOLD", "WATCH"),
        "FAST_GROWER",
    ),
    "KO": (
        "The Coca-Cola Company",
        ("AVOID", "AVOID", "HOLD", "BUY", "AVOID", "WATCH", "BUY", "AVOID"),
        "SLOW_GROWER",
    ),
    "JNJ": (
        "Johnson & Johnson",
        ("BUY", "AVOID", "BUY", "AVOID", "BUY", "HOLD", "WATCH", "AVOID"),
        "STALWART",
    ),
    "JPM": (
        "JPMorgan Chase & Co.",
        ("INSUFFICIENT_DATA",) * 8,
        "UNKNOWN",
    ),
    "XOM": (
        "Exxon Mobil Corporation",
        ("BUY", "BUY", "AVOID", "AVOID", "BUY", "AVOID", "BUY", "AVOID"),
        "CYCLICAL",
    ),
    "PLD": (
        "Prologis, Inc.",
        ("BUY", "BUY", "BUY", "BUY", "BUY", "BUY", "AVOID", "HOLD"),
        "ASSET_PLAY",
    ),
    "TSLA": (
        "Tesla, Inc.",
        ("AVOID", "AVOID", "AVOID", "AVOID", "AVOID", "AVOID", "HOLD", "AVOID"),
        "FAST_GROWER",
    ),
}

#: 22 extra companies, deterministic verdict rotation (no RNG).
EXTRA_COMPANIES: dict[str, str] = {
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com, Inc.",
    "META": "Meta Platforms, Inc.",
    "BRK.B": "Berkshire Hathaway Inc.",
    "V": "Visa Inc.",
    "MA": "Mastercard Incorporated",
    "UNH": "UnitedHealth Group Incorporated",
    "HD": "The Home Depot, Inc.",
    "PG": "The Procter & Gamble Company",
    "DIS": "The Walt Disney Company",
    "NFLX": "Netflix, Inc.",
    "NVDA": "NVIDIA Corporation",
    "AMD": "Advanced Micro Devices, Inc.",
    "INTC": "Intel Corporation",
    "BA": "The Boeing Company",
    "CAT": "Caterpillar Inc.",
    "MCD": "McDonald's Corporation",
    "NKE": "NIKE, Inc.",
    "PEP": "PepsiCo, Inc.",
    "WMT": "Walmart Inc.",
    "CVX": "Chevron Corporation",
    "GE": "GE Aerospace",
}

_ROTATION = ("BUY", "BUY", "WATCH", "AVOID", "HOLD", "BUY", "AVOID", "WATCH")
_CATEGORIES = (
    "SLOW_GROWER",
    "STALWART",
    "FAST_GROWER",
    "CYCLICAL",
    "TURNAROUND",
    "ASSET_PLAY",
)

#: Deterministic demo prices (the 8 demo tickers use the pinned bundle values).
_DEMO_PRICES = {
    "AAPL": 340.0,
    "MSFT": 510.0,
    "KO": 70.0,
    "JNJ": 165.0,
    "JPM": 300.0,
    "XOM": 120.0,
    "PLD": 115.0,
    "TSLA": 420.0,
    "GOOGL": 195.0,
    "AMZN": 225.0,
    "META": 600.0,
    "BRK.B": 480.0,
    "V": 310.0,
    "MA": 520.0,
    "UNH": 340.0,
    "HD": 400.0,
    "PG": 165.0,
    "DIS": 115.0,
    "NFLX": 900.0,
    "NVDA": 180.0,
    "AMD": 160.0,
    "INTC": 35.0,
    "BA": 220.0,
    "CAT": 400.0,
    "MCD": 300.0,
    "NKE": 75.0,
    "PEP": 150.0,
    "WMT": 100.0,
    "CVX": 155.0,
    "GE": 260.0,
}


def _row(ticker: str, name: str, verdicts: tuple[str, ...], category: str) -> dict:
    counts = {verdict: verdicts.count(verdict) for verdict in set(verdicts)}
    buy = counts.get("BUY", 0)
    avoid = counts.get("AVOID", 0)
    price = _DEMO_PRICES.get(ticker)
    return {
        "name": name,
        "verdicts": dict(zip(METHODOLOGY_KEYS, verdicts, strict=True)),
        "buy_count": buy,
        "avoid_count": avoid,
        "insufficient_count": counts.get("INSUFFICIENT_DATA", 0),
        "na_count": counts.get("N/A", 0),
        "consensus_score": buy - avoid,
        "lynch_category": category,
        "price": price,
        "prices_available": price is not None,
    }


def build() -> dict:
    companies: dict[str, dict] = {
        ticker: _row(ticker, name, verdicts, category)
        for ticker, (name, verdicts, category) in DEMO_COMPANIES.items()
    }
    for index, (ticker, name) in enumerate(EXTRA_COMPANIES.items()):
        verdicts = tuple(
            _ROTATION[(position + index) % len(_ROTATION)]
            for position in range(len(METHODOLOGY_KEYS))
        )
        companies[ticker] = _row(
            ticker, name, verdicts, _CATEGORIES[index % len(_CATEGORIES)]
        )
    prices_snapshot = {ticker: _DEMO_PRICES[ticker] for ticker in sorted(_DEMO_PRICES)}
    return {
        "version": 2,
        "date": datetime.now(UTC).date().isoformat(),
        "universe": "sp500",
        "prices_available": bool(prices_snapshot),
        "prices_snapshot": prices_snapshot,
        "companies": {ticker: companies[ticker] for ticker in sorted(companies)},
    }


def main() -> None:
    payload = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON: it is a generated machine fixture inside the size-capped
    # demo bundle (see test_demo_mode.test_bundle_is_complete_and_small).
    OUTPUT.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT} ({len(payload['companies'])} companies)")


if __name__ == "__main__":
    main()
