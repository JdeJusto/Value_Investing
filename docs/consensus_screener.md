# Consensus screener — design

## Purpose

The consensus screener answers one question: **"which companies does the
multi-methodology system actually like?"** It aggregates the verdicts of all
eight book methodologies over a whole universe, so agreement (and
disagreement) becomes visible at a glance.

It is **not** a replacement for the existing screener:

| Lens | Question | Scope |
| --- | --- | --- |
| Screener (`03_screener.py`) | Which companies pass *one* methodology's numeric filters? | One methodology, universe-wide |
| `compare-methodologies` (CLI) | What do the eight methodologies say about *one* company? | One company, deep |
| **Consensus** | Which companies have the most BUY/AVOID agreement across the eight? | Eight methodologies, universe-wide |

Disagreement is deliberately first-class: the "disagreement zone" lists
companies where some frameworks say BUY while others say AVOID. That is
exactly where the user's judgment matters most.

## Data flow

The computation is expensive (8 methodologies x N companies), so the primary
model is **weekly precompute**:

1. `scripts/compute_consensus_rankings.py --universe sp500` reads the
   universe, fetches fundamentals from Financial-DataBase (sequential reads),
   evaluates the eight methodologies (bounded `ThreadPoolExecutor`, 4
   workers) and writes `data/consensus/consensus_<date>.json`.
2. `ConsensusService` reads the JSON for the UI/CLI and derives rankings.
3. Ad-hoc runs use the same script with `--universe`, `--limit` and
   `--date`; rerunning a date overwrites cleanly (idempotent).

A file older than 30 days is treated as stale (the service refuses it and the
UI shows the empty state). Financial-DataBase is only read; no prices are
fetched — price-dependent criteria degrade to their no-price path, which keeps
the computation deterministic and network-free.

## Output format

```json
{
  "version": 1,
  "date": "2026-10-06",
  "universe": "sp500",
  "companies": {
    "AAPL": {
      "name": "Apple Inc.",
      "verdicts": {
        "buffett_classic": "WATCH",
        "buffett_clark": "BUY",
        "fisher_quantitative_subset": "BUY",
        "graham": "AVOID",
        "graham_dodd": "AVOID",
        "greenblatt": "HOLD",
        "lynch_garp": "AVOID",
        "marks": "AVOID"
      },
      "buy_count": 2,
      "avoid_count": 4,
      "insufficient_count": 0,
      "consensus_score": -2,
      "lynch_category": "STALWART"
    }
  }
}
```

`consensus_score = buy_count - avoid_count`. HOLD/WATCH/INSUFFICIENT do not
add to either side. `lynch_category` comes from the `lynch_garp`
methodology's category label (`UNKNOWN` when it does not apply, e.g. banks).

## Ranking logic

- **Top by consensus**: sort by `buy_count` desc, then `consensus_score`
  desc, then `avoid_count` asc, then ticker. Companies where every
  methodology returned INSUFFICIENT (pure data holes) are excluded.
- **Best per Lynch category**: the same ordering grouped by
  `lynch_category`; categories with fewer than N companies with a BUY fall
  back to the top by `consensus_score`.
- **Disagreement zone**: companies with 3-5 BUYs and 3-5 AVOIDs; the two
  camps are roughly balanced, so neither agreement nor rejection dominates.
- **NO-consensus filter**: all-INSUFFICIENT companies are skipped everywhere;
  they are a data-coverage signal, not an investment view.

## CLI and UI

- **CLI (follow-up)**: `consensus <ticker>`, `consensus-ranking --universe`,
  `consensus-by-category --universe`. The JSON file is the source for all
  three.
- **UI**: page `06_consensus.py` with a universe/date/category filter, the
  top-by-consensus table (CSV download), the six Lynch-category blocks, the
  disagreement zone and the full verdict matrix (BUY green / AVOID red).

## Demo mode

`data/demo/consensus/consensus_demo.json` ships a deterministic 30-company
sample (the 8 demo tickers plus 22 synthetic) built by
`scripts/build_demo_consensus.py`, so the page renders offline.
