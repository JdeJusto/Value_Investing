"""One searchable catalog of the CLI commands.

The interactive menu, ``vi help --search`` and the categorized ``vi --help``
footer all read this file, so a command's description and example live in one
place. It is deliberately data-only: no imports from ``cli.commands`` (which
would make the catalog heavy) and no business logic.

A test pins the catalog against the real argparse subcommands, so adding a
command without registering it here fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Display order for the grouped help and the menu.
CATEGORY_ORDER = (
    "Analysis",
    "Ranking & screening",
    "Portfolio",
    "Data & refresh",
    "Backtesting",
    "Debug & misc",
)


@dataclass(frozen=True)
class CommandInfo:
    """A command's user-facing catalog entry."""

    name: str
    category: str
    summary: str
    example: str
    keywords: tuple[str, ...] = ()


CATALOG: dict[str, CommandInfo] = {
    # --- Analysis ---------------------------------------------------------
    "scorecard": CommandInfo(
        "scorecard",
        "Analysis",
        "Six-dimension scorecard with verdicts and the rules behind them",
        "vi scorecard AAPL",
        ("score", "analysis", "dimensions", "report", "quality"),
    ),
    "financials": CommandInfo(
        "financials",
        "Analysis",
        "Hierarchical T-view balance sheet (assets, liabilities, equity)",
        "vi financials AAPL",
        ("balance", "assets", "liabilities", "equity", "t-view"),
    ),
    "dcf": CommandInfo(
        "dcf",
        "Analysis",
        "Two-stage DCF valuation (not-from-canon)",
        "vi dcf AAPL",
        ("valuation", "intrinsic", "cash flow", "fair value"),
    ),
    "methodologies": CommandInfo(
        "methodologies",
        "Analysis",
        "List methodologies or show one methodology's rules",
        "vi methodologies show graham",
        ("methodology", "list", "rules", "show"),
    ),
    "analyze": CommandInfo(
        "analyze",
        "Analysis",
        "Full analysis: ratios, scoring and DCF in detail",
        "vi analyze AAPL",
        ("analysis", "ratios", "score"),
    ),
    "analyze-full": CommandInfo(
        "analyze-full",
        "Analysis",
        "Consolidated six-section report per ticker",
        "vi analyze-full AAPL --no-prices",
        ("analysis", "report", "overview"),
    ),
    "analyze-graham": CommandInfo(
        "analyze-graham",
        "Analysis",
        "Graham defensive-investor screen",
        "vi analyze-graham AAPL",
        ("graham", "value", "methodology"),
    ),
    "analyze-graham-dodd": CommandInfo(
        "analyze-graham-dodd",
        "Analysis",
        "Graham & Dodd deep-value screen",
        "vi analyze-graham-dodd AAPL",
        ("graham", "dodd", "deep value", "methodology"),
    ),
    "analyze-buffett-classic": CommandInfo(
        "analyze-buffett-classic",
        "Analysis",
        "Buffett/Munger four-pillar quality filter",
        "vi analyze-buffett-classic AAPL",
        ("buffett", "quality", "methodology"),
    ),
    "analyze-buffett-clark": CommandInfo(
        "analyze-buffett-clark",
        "Analysis",
        "Buffett/Clark durable competitive advantage rules",
        "vi analyze-buffett-clark AAPL",
        ("buffett", "clark", "moat", "methodology"),
    ),
    "analyze-fisher-quant": CommandInfo(
        "analyze-fisher-quant",
        "Analysis",
        "Fisher's four quantifiable points",
        "vi analyze-fisher-quant AAPL",
        ("fisher", "quality", "r&d", "methodology"),
    ),
    "analyze-lynch-garp": CommandInfo(
        "analyze-lynch-garp",
        "Analysis",
        "Lynch GARP screen",
        "vi analyze-lynch-garp AAPL",
        ("lynch", "garp", "growth", "methodology"),
    ),
    "analyze-greenblatt": CommandInfo(
        "analyze-greenblatt",
        "Analysis",
        "Greenblatt Magic Formula ranking lookup",
        "vi analyze-greenblatt AAPL",
        ("greenblatt", "magic formula", "methodology"),
    ),
    "analyze-marks": CommandInfo(
        "analyze-marks",
        "Analysis",
        "Howard Marks measurable rules",
        "vi analyze-marks AAPL",
        ("marks", "cycle", "methodology"),
    ),
    "buffett-analysis": CommandInfo(
        "buffett-analysis",
        "Analysis",
        "Buffett analysis: moat, financial strength and composite score",
        "vi buffett-analysis AAPL",
        ("buffett", "moat", "quality", "score"),
    ),
    "historical-valuation": CommandInfo(
        "historical-valuation",
        "Analysis",
        "Historical P/E and FCF yield",
        "vi historical-valuation AAPL",
        ("history", "p/e", "fcf", "valuation"),
    ),
    "compare-methodologies": CommandInfo(
        "compare-methodologies",
        "Analysis",
        "All methodologies side by side for one company",
        "vi compare-methodologies AAPL",
        ("methodologies", "compare", "disagreement"),
    ),
    "company": CommandInfo(
        "company",
        "Analysis",
        "Name, sector/industry, price and key metrics",
        "vi company META",
        ("company", "sector", "industry", "profile"),
    ),
    "opportunities": CommandInfo(
        "opportunities",
        "Analysis",
        "Detected opportunities: cheap quality, compounders, turnarounds",
        "vi opportunities --type COMPOUNDERS",
        ("opportunities", "screener", "compounders", "turnarounds"),
    ),
    "anomalies": CommandInfo(
        "anomalies",
        "Analysis",
        "Anomalies in the latest fiscal year's fundamentals",
        "vi anomalies AAPL",
        ("anomalies", "outliers", "quality"),
    ),
    "momentum": CommandInfo(
        "momentum",
        "Analysis",
        "Ranking by fundamental momentum",
        "vi momentum",
        ("momentum", "ranking", "trend"),
    ),
    "alerts": CommandInfo(
        "alerts",
        "Analysis",
        "Buy/sell signals and fundamental trigger events",
        "vi alerts AAPL",
        ("alerts", "signals", "triggers"),
    ),
    "interactive": CommandInfo(
        "interactive",
        "Analysis",
        "Open the guided interactive command menu",
        "vi interactive",
        ("menu", "interactive", "help"),
    ),
    # --- Ranking & screening ---------------------------------------------
    "rank": CommandInfo(
        "rank",
        "Ranking & screening",
        "Top N tickers by methodology (or an AND/OR combination)",
        "vi rank --by graham --top 20",
        (
            "top",
            "top 20",
            "ranking",
            "methodology",
            "graham",
            "lynch",
            "buffett",
            "combine",
        ),
    ),
    "screener": CommandInfo(
        "screener",
        "Ranking & screening",
        "Fundamental screener with filters and methodology verdicts",
        "vi screener --methodology graham:BUY --top 20",
        ("screen", "filter", "methodology", "buy"),
    ),
    "consensus": CommandInfo(
        "consensus",
        "Ranking & screening",
        "One ticker's consensus across the methodologies",
        "vi consensus AAPL --universe all",
        ("consensus", "all methodologies", "verdicts"),
    ),
    "consensus-ranking": CommandInfo(
        "consensus-ranking",
        "Ranking & screening",
        "Rank the consensus file by buys, avoids or score",
        "vi consensus-ranking --universe sp500 --top 10",
        ("consensus", "ranking", "top"),
    ),
    "consensus-by-category": CommandInfo(
        "consensus-by-category",
        "Ranking & screening",
        "Top companies per Lynch category by consensus score",
        "vi consensus-by-category --universe sp500",
        ("consensus", "category", "lynch"),
    ),
    # --- Portfolio --------------------------------------------------------
    "portfolio": CommandInfo(
        "portfolio",
        "Portfolio",
        "Positions, PnL, allocation and risk concentration",
        "vi portfolio view",
        ("portfolio", "positions", "pnl", "holdings"),
    ),
    "watchlist": CommandInfo(
        "watchlist",
        "Portfolio",
        "Persistent watchlist enriched with scores and signals",
        "vi watchlist list",
        ("watchlist", "monitoring", "candidates"),
    ),
    "backtest": CommandInfo(
        "backtest",
        "Backtesting",
        "Backtest a methodology's signals (PoC) or a yearly strategy",
        "vi backtest --methodology graham --years 5",
        ("backtest", "methodology", "performance", "history"),
    ),
    # --- Data & refresh ---------------------------------------------------
    "refresh": CommandInfo(
        "refresh",
        "Data & refresh",
        "Refresh SEC facts and the current price for one ticker",
        "vi refresh AAPL",
        ("refresh", "sync", "prices", "facts"),
    ),
    "load-data": CommandInfo(
        "load-data",
        "Data & refresh",
        "Download, normalize and persist historical financial data",
        "vi load-data AAPL --years 10",
        ("load", "download", "sync", "history"),
    ),
    "data-status": CommandInfo(
        "data-status",
        "Data & refresh",
        "Coverage, quality and freshness for a ticker",
        "vi data-status AAPL",
        ("status", "coverage", "freshness", "quality"),
    ),
    "filings": CommandInfo(
        "filings",
        "Data & refresh",
        "Official SEC filings with EDGAR links",
        "vi filings AAPL --form 10-K",
        ("filings", "sec", "10-k", "edgar"),
    ),
    "filing-balance-sheet": CommandInfo(
        "filing-balance-sheet",
        "Data & refresh",
        "Balance sheet extracted from a filing",
        "vi filing-balance-sheet AAPL",
        ("filing", "balance", "10-k"),
    ),
    "filing-statement": CommandInfo(
        "filing-statement",
        "Data & refresh",
        "Any financial statement extracted from a filing",
        "vi filing-statement AAPL --type income_statement",
        ("filing", "statement", "income", "cash flow"),
    ),
    "filing-income-statement": CommandInfo(
        "filing-income-statement",
        "Data & refresh",
        "Income statement extracted from a filing",
        "vi filing-income-statement AAPL",
        ("filing", "income", "statement"),
    ),
    "filing-cash-flow": CommandInfo(
        "filing-cash-flow",
        "Data & refresh",
        "Cash flow statement extracted from a filing",
        "vi filing-cash-flow AAPL",
        ("filing", "cash flow", "statement"),
    ),
    "filing-section": CommandInfo(
        "filing-section",
        "Data & refresh",
        "Narrative section (Risk Factors, MD&A) from a filing",
        "vi filing-section AAPL --type md_a",
        ("filing", "risk factors", "md&a", "narrative"),
    ),
    "financial-alerts": CommandInfo(
        "financial-alerts",
        "Data & refresh",
        "Deterministic alerts: cash runway, margins, debt, FCF",
        "vi financial-alerts AAPL",
        ("alerts", "financial", "risk"),
    ),
    # --- Debug & misc -----------------------------------------------------
    "sql-analysis": CommandInfo(
        "sql-analysis",
        "Debug & misc",
        "Run reusable SQL scripts from Financial-DataBase",
        "vi sql-analysis --list",
        ("sql", "analysis", "fdb"),
    ),
    "debug": CommandInfo(
        "debug",
        "Debug & misc",
        "System diagnostics and quick tests",
        "vi debug",
        ("debug", "diagnostics", "health"),
    ),
}

#: Common wrong names / intents mapped to the real command.
INTENT_ALIASES: dict[str, str] = {
    "top": "rank",
    "ranking": "rank",
    "rankings": "rank",
    "scores": "scorecard",
    "balance": "financials",
    "valuation": "dcf",
    "menu": "interactive",
    "screen": "screener",
    "consensus-all": "consensus-ranking",
}

#: A short "what do you want to do?" block reused by --help and the menu.
COMMON_TASKS: tuple[tuple[str, str], ...] = (
    ("Top 20 by methodology", "vi rank --by graham --top 20"),
    ("Balance sheet", "vi financials AAPL"),
    ("Full scorecard", "vi scorecard AAPL"),
    ("Compare methodologies", "vi compare-methodologies AAPL"),
    ("Refresh one ticker", "vi refresh AAPL"),
    ("Consensus", "vi consensus AAPL --universe all"),
    ("Screener by verdict", "vi screener --methodology graham:BUY"),
    ("Backtest a methodology", "vi backtest --methodology graham --years 5"),
)


def commands_in_category(category: str) -> list[CommandInfo]:
    """Catalog entries of one category, in name order."""
    return sorted(
        (info for info in CATALOG.values() if info.category == category),
        key=lambda info: info.name,
    )


def format_catalog() -> str:
    """The categorized command list used by the help footer/menu."""
    lines = []
    for category in CATEGORY_ORDER:
        entries = commands_in_category(category)
        if not entries:
            continue
        lines.append(f"{category}:")
        for info in entries:
            lines.append(f"  {info.name:<26} {info.summary}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_common_tasks() -> str:
    """The quick "what do you want to do?" table as plain text."""
    lines = ["Common tasks:"]
    for label, example in COMMON_TASKS:
        lines.append(f"  {example:<52} # {label}")
    return "\n".join(lines)
