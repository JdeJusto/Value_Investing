# Methodology Ranking Design (Option D - Approved)

## 1) Overview
New page `ui/pages/07_methodologies.py` with **two tabs**:
- **By methodology**: rank all tickers in a selected universe by a single methodology (score desc, with verdict tiebreaker).
- **Combine**: select a subset of methodologies and combine them with a strategy (AND / OR / Weighted). 

This reuses existing building blocks:
- `backend.methodologies.registry` (discover/list/get)
- `backend.services.ui_adapter.run_methodologies()` (single-ticker evaluation path)
- `METHODOLOGY_KEYS` / aggregation ideas from `scripts/compute_consensus_rankings.py`
- UI components: `dataframe_with_download`, `page_header`, etc.

## 2) Tab structure (mockups)

### Tab "By methodology"
```
┌────────────────────────────────────────────────────────────┐
│ Methodologies                                              │
├────────────────────────────────────────────────────────────┤
│ [By methodology] [Combine]                                 │
│                                                            │
│ Methodology: [Graham ▾]                                    │
│ Universe:    [Demo (76) ▾]                                 │
│ Top N:       [20 ▾]                                        │
│                                                            │
│ Showing top 20 by Graham score.                            │
│ Note: 8 tickers N/A (financials / insufficient data).     │
│                                                            │
│ Rank  Ticker  Family       Verdict  Score  Action          │
│ ────  ──────  ───────────  ───────  ─────  ──────          │
│  1    AAPL    DEEP_VALUE   BUY      9.2    [View →]        │
│  2    MSFT    DEEP_VALUE   BUY      8.9    [View →]        │
│  ...                                                       │
│                                                            │
│ [Download CSV]                                             │
└────────────────────────────────────────────────────────────┘
```

### Tab "Combine"
```
┌────────────────────────────────────────────────────────────┐
│ Methodologies                                              │
├────────────────────────────────────────────────────────────┤
│ [By methodology] [Combine]                                 │
│                                                            │
│ Methodologies: ☑Graham ☑Lynch ☐Buffett ☐Greenblatt ...    │
│ Strategy:      (•) AND  ( ) OR  ( ) Weighted               │
│ Universe:      [Demo (76) ▾]                               │
│ Top N:         [20 ▾]                                      │
│                                                            │
│ 12 tickers pass Graham AND Lynch (BUY or WATCH in both).   │
│                                                            │
│ Rank  Ticker  Graham       Lynch        Combined           │
│ ────  ──────  ───────────  ───────────  ────────           │
│  1    AAPL    BUY 9.2      BUY 8.5      8.85               │
│  2    MSFT    BUY 8.9      WATCH 7.2    8.05               │
│  ...                                                       │
│                                                            │
│ [Download CSV]                                             │
└────────────────────────────────────────────────────────────┘
```

## 3) Backend service

Create `backend/services/methodology_ranking_service.py`.

### Data structures
```python
from dataclasses import dataclass
from backend.methodologies.base import Verdict


@dataclass
class RankedTicker:
    ticker: str
    verdict: Verdict
    score: float | None
    family: str
    n_a_reason: str | None  # None if scored/evaluable, else why it's N/A


@dataclass
class CombinedRankedTicker:
    ticker: str
    per_methodology: dict[str, RankedTicker]
    combined_score: float | None
    combined_verdict: Verdict
    rationale: str  # human-readable explanation
```

### Functions
```python
def rank_by_methodology(
    methodology: str,
    universe: list[str],
    top_n: int = 20,
    *,
    include_na: bool = False,
) -> list[RankedTicker]:
    """Return top_n tickers by the given methodology."""

def rank_combined(
    methodologies: list[str],
    universe: list[str],
    strategy: str,  # "and" | "or" | "weighted"
    top_n: int = 20,
    *,
    weights: dict[str, float] | None = None,
) -> list[CombinedRankedTicker]:
    """Return top_n tickers matching the strategy."""
```

### Design notes
- **Reuse**: call `backend.methodologies.registry.discover()`, `registry.get()`, and `backend.services.ui_adapter.run_methodologies()` (or equivalent). 
- **Batch**: evaluate all tickers in the universe for the requested methodologies. Do **not** duplicate the entire script flow of `scripts/compute_consensus_rankings.py`; only reuse small helpers where sensible (e.g. universe parsing/aggregation ideas). If coupling is heavy, inline minimal batch logic in the service.
- **N/A handling**: treat `Verdict.N_A` / `INSUFFICIENT_DATA` as non-rankable by default. `include_na=False` excludes them; when excluded, surface a caption "N tickers N/A (financials / insufficient data)". 
- **Ordering**: score desc → verdict tiebreaker (BUY > WATCH > HOLD > AVOID) → items without score but with verdict → N/A/excluded last (with note).
- **AND**: require verdict ∈ {BUY, WATCH} in **all** selected methodologies.
- **OR**: require verdict ∈ {BUY, WATCH} in **at least one** selected methodology.
- **Weighted**: only consider tickers with **numeric score in all** selected methodologies. Verdict normalization (BUY=4, WATCH=3, HOLD=2, AVOID=1) **only if explicitly opted in** by the user (not default). Default weights = equal.
- **Cache**: cache at service level if pure, but **UI must use `st.cache_data(ttl=3600)`** for the full batch results (keyed by universe hash + methodology selection + strategy). Add a manual "Refresh" button.

## 4) UX decisions
- **AND by default** in "Combine" (stricter, less noisy, matches "pass in both" use case).
- **Exclude N/A by default** from top N with explicit caption listing count and reason.
- **Session state**: persist selected methodologies, strategy, universe, top N across tab switches.
- **Navigation**: `st.link_button`/`st.page_link` to Analysis page for each ticker.
- **Export**: use `dataframe_with_download` for both tabs. "Combine" CSV should include per-methodology columns (verdict/score) plus `combined_score` and `rationale`.
- **Universe dropdown**: selectable (Demo/Live or available universes), not hardcoded to 76.

## 5) Tests (planned)
- `test_rank_by_methodology_returns_top_n`
- `test_rank_by_methodology_excludes_na`
- `test_rank_combined_and_requires_all_buy_or_watch`
- `test_rank_combined_or_includes_any`
- `test_rank_combined_weighted_requires_numeric_scores`
- `test_na_ticker_not_ranked_as_avoid`

## 6) Estimated cost
| Component | Lines | Notes |
|-----------|-------|-------|
| `backend/services/methodology_ranking_service.py` | ~80-120 | Core logic, reuse `run_methodologies` |
| `ui/pages/07_methodologies.py` | ~150-200 | Two tabs, cache, export, navigation |
| Tests (`tests/unit/test_methodology_ranking.py`) | ~80-120 | As above |
| Docs/assets (screenshot if needed) | small | Follow verification rules |
| **Total** | **~310-440** | ~3-4h |

## 7) Open questions (resolved by directives)
- **AND vs Weighted default**: AND (approved).
- **N/A display**: exclude by default, show caption (approved).
- **Cache TTL**: UI `st.cache_data(ttl=3600)` + manual Refresh (approved).
- **CSV columns (Combine)**: include per-methodology + combined + rationale (approved).

**STOP 2 — awaiting approval before Fase 2.**
