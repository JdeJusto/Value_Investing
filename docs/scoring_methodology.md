# Screener Scoring Methodology

This document describes how the investment screener derives a single 0-100
ranking score (`rank_score`) for every analyzed company, how it maps score
to a signal, and the calibration rules that keep the scale meaningful across
a large universe.

## Pipeline

```
ScreenedCompany
   ├─ composite_score       Absolute quality blend (scoring_model)
   ├─ dcf_margin_of_safety  Valuation vs DCF (analytics service)
   ├─ buffett_score         Buffett-style quality 0-100
   ├─ moat_analysis         Economic moat classification
   ├─ quality_metrics       ROIC, ROE, leverage, coverage, FCF ...
   ├─ delta_metrics         Year-over-year momentum deltas
   └─ health_penalties      Capping for weak balance sheets
        ↓
   component_scores(item)   Six absolute 0-100 components
        ↓
   percentile-rank each component within the analyzed universe
        ↓
   weight (quality 55%, value 20%, momentum 10%, growth 5%,
           stability 5%, confidence 5%)
        ↓
   map onto [10, 90]  →  calibrated rank
        ↓
   health-capped  →  max 60 for negative FCF / D/E>=1.5 / coverage<3
        ↓
   classify signal: BUY >= 75, WATCHLIST >= 60, AVOID < buffett 40
```

## Scoring components

| Component    | Weight | Source                                                  |
|--------------|--------|---------------------------------------------------------|
| Quality      | 0.55   | Composite score total (scoring_model `composite_score`) |
| Value        | 0.20   | Margin of safety vs DCF (`dcf_margin_of_safety`)        |
| Momentum     | 0.10   | `delta_metrics` YoY deltas                              |
| Growth       | 0.05   | Buffett pillars: cash generation + profitability        |
| Stability    | 0.05   | Buffett pillar: stability (earnings variability)        |
| Confidence   | 0.05   | Data confidence level (LOW/MEDIUM/HIGH)                 |

Quality **plus** value (0.75 combined) outweigh momentum by design, so the
ranking rewards the strongest company over the cheapest one. A heavily
levered or cash-burning company can never reach the top band.

## Calibrated rank

`calibrated_rank(item, items)` in `backend/screener/ranking_engine.py`:

1. Computes absolute `component_scores(item)` for every company in the pool.
2. Percentile-ranks each component within the pool (ties share ranks).
3. Blends with the component weights, then maps the 0-1 blend linearly onto
   the `[CALIBRATION_MIN=10, CALIBRATION_MAX=90]` band.
4. Caps the result with `health_cap` at `LEVERAGED_RANK_CAP=60` when:
   - free cash flow is negative, or
   - debt-to-equity is at least 1.5, or
   - interest coverage is below 3x.

`rank_score(item)` (0-100, non-normalized) is kept for backward
compatibility and for ranking the opportunities engine.

## Data-quality fallback

`backend/analytics/service.py::_data_reliability()` produces a [0,1]
`coverage` and a `data_quality_score`.

- When the database provider supplies `data_quality_score`, it is used
  directly.
- When it is `None` (e.g. FDB derives fundamentals from SEC facts without a
  quality figure), quality is derived from history depth:
  `quality = min(len(used_years), REQUIRED_HISTORY_YEARS) / 8`, so a company
  with eight years of completed fiscal data scores 1.0.
- `confidence_level()` (`backend/intelligence/scoring_model.py`) maps
  quality + coverage to LOW / MEDIUM / HIGH confidence:
  - `quality < 0.3` or `coverage < 0.5`  → LOW
  - `quality < 0.7` or `coverage < 0.8`  → MEDIUM
  - otherwise                           → HIGH

The confidence level feeds the 5% confidence component and the signal
channels (a BUY rests on HIGH/at least MEDIUM confidence).

## Signals

Defined in `backend/screener/signals.py` (thresholds are on the calibrated
`rank_score`):

| Signal     | Condition                          |
|------------|------------------------------------|
| BUY        | `rank_score >= 75`                 |
| WATCHLIST  | `60 <= rank_score < 75`            |
| HOLD       | `40 <= rank_score < 60`            |
| AVOID      | `rank_score < 40` or buffett < 40  |

The AVOID lower bound is anchored to buffett_score < 40 (weak company),
not just a low calibrated rank.

## Alerts and trigger calibration

The daily workflow evaluates three alert types in `backend/alerts`
(`run()` in `alert_engine.py`), summarized in `docs/runbook_daily.md`:

| Alert          | Condition                                                        |
|----------------|------------------------------------------------------------------|
| `BUY_SIGNAL`   | signal is BUY (`rank >= 75`, composite `>= 70`, confidence HIGH/MEDIUM, buffett `>= 50`) |
| `SELL_WARNING` | composite `total_score` drops `>= 10` (HIGH `>= 15`) vs the previous day's state |
| `TRIGGER_EVENT`| dominant *positive* fundamental improvement clearing both floors below |

### TRIGGER_EVENT calibration

Defined in `backend/screener/signals.py`. A trigger fires only for the
dominant **positive** improvement of the latest period when:

1. its raw delta clears an **absolute floor**:
   - `MARGIN_EXPANSION` — gross margin `>= +2 pp`
   - `REVENUE_ACCELERATION` — revenue growth-rate acceleration `>= +5 pp`
   - `ROIC_IMPROVEMENT` — ROIC `>= +3 pp`
   - `FCF_SURGE` — FCF growth `>= +20%` **and** FCF itself positive
2. it also clears a **cross-sectional percentile floor** of that delta
   across the analyzed universe (`calibrate_trigger_thresholds`, default
   quantile `q = 0.92`, effective threshold `= max(floor, percentile)`).
   With fewer than 20 analyses the universe percentile is skipped and the
   absolute floors apply alone (deterministic single-company behavior).
3. the improvement is **persistent** where data permits: two consecutive
   periods moving up (`gross_margin_delta_prev`, `roic_delta_prev`, and two
   consecutive positive revenue-growth years).

Deterioration is deliberately **not** a `TRIGGER_EVENT` — score drops
(`SELL_WARNING`) and anomaly reporting cover it. Expected counts on the
~500-company universe: `TRIGGER_EVENT` ≈ 6-12% (30-60 observed 58 on
2026-09-22, ceiling 80), `BUY_SIGNAL` ≈ 10-40, `SELL_WARNING` ≈ 0-5 and only when
scores really drop ≥ 10 points vs the previous day (0 fires when the
universe is stable).

## Calibration targets

| Universe position | Target score band |
|-------------------|-------------------|
| Best              | 75 - 95           |
| Average           | 40 - 60           |
| Weakest           | 10 - 35           |

Because the rank is cross-sectional, at least one company in every analyzed
universe lands near the top and one near the bottom — the scale always
spans ~10-90 and never compresses to a narrow range.

## Related files

- `backend/intelligence/scoring_model.py` — composite quality blend, confidence
- `backend/analytics/service.py` — MOS (market-cap based), data reliability,
  in-progress-year filtering
- `backend/screener/ranking_engine.py` — components, percentile rank, health cap
- `backend/screener/signals.py` — signal thresholds
- `backend/screener/screener_service.py` — `_screen` orchestration
- `scripts/daily_workflow.py` — daily universe report
- `docs/scoring_validation.md` — empirical validation on a 20-ticker universe