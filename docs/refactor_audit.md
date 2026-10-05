# Refactor audit (v0.10.0 session)

Audit of file sizes and duplication before the Financial Insights feature
and the modularity refactor. This document is the plan for Phases D/E; it is
committed with the docs at the end of the session.

## Top 10 largest files

| # | File | Lines | Dominant symbols |
| --- | --- | --- | --- |
| 1 | `backend/repositories/financial_database_repository.py` | 2174 | `FinancialDatabaseRepository` (1770), concept-mapping constants (~310) |
| 2 | `backend/methodologies/lynch_garp/methodology.py` | 983 | `LynchGARPMethodology` (847) |
| 3 | `backend/services/price_service.py` | 972 | `PriceService` (812) |
| 4 | `backend/valuation/dcf.py` | 962 | `DCFValuation` (901) |
| 5 | `backend/services/refresh_service.py` | 954 | `RefreshService` (431), `FdbGateway` (242), `load_refresh_config` (99) |
| 6 | `backend/services/ui_adapter.py` | 921 | many 50–65-line functions (`enrich_rows` 65, `build_portfolio_view` 57, `disagreement_narrative` 52, `build_methodologies_view` 51) |
| 7 | `backend/app/cli.py` | 646 | service construction, refresh args, repo builders |
| 8 | `ui/pages/02_analysis.py` | 632 | page render functions (single-page UI) |
| 9 | `cli/commands/screener.py` | 573 | screener command |
| 10 | `backend/methodologies/graham/methodology.py` | 523 | `GrahamMethodology` |

Also >500: `backend/analytics/service.py` (523), `backend/services/yahoo_health.py`
(521), `backend/services/financial_statement_parser.py` (519). Total
`backend/ cli/ ui/`: 34,376 lines.

## Duplication found

| Candidate | Count | Verdict |
| --- | --- | --- |
| `_verdict_color` (method verdicts → colors) | 9 commands | **Identical** (BUY/WATCH/HOLD/AVOID/INSUFFICIENT_DATA). Extract. |
| `_confidence_color` (HIGH/MEDIUM/LOW → colors) | 6 commands | **Identical**. Extract. |
| `_SOURCE_LABELS` (`toc_anchor`/`text_search` labels) | 2 modules | **Identical**. Extract. |
| `_VERDICT_COLORS` in `cli/commands/dcf.py` | 1 | **Not duplication**: DCF verdicts (UNDERVALUED/FAIR/OVERVALUED) are a different vocabulary — do not merge. |
| `_red_flags` / `_reasons` / `_metrics` | 5 methodologies | Per-methodology rule logic, different bodies. No action. |
| `METHODOLOGY` / `ALL_RULES` | 6–8 modules | Per-module namespacing (each methodology owns its rules). No action. |
| `DEFAULT_TAX_RATE/WACC/MARKET_RETURN` | `backend/config/settings.py`, `backend/core/config.py`, `analytics/service.py`, `quality_metrics.py` | Overlap between the two config modules is real but they expose **different APIs** (settings: get_sec_email raising; core: env-driven constants). Consolidation is not a pure move — deferred (documented here). |
| `ROIC_FLOOR`, `GROSS_CV_STABLE/UNSTABLE`, `STABILITY_WEIGHT`, `MARGIN_WEIGHT` | moat_analysis vs buffett_engine vs ranking_engine | Same names, **different tuned values** — merging would change scoring. No action. |
| Value formatters (`format_fact_value`, `format_value`, `_format_metric`, `fmt_money_short`, `fmt_or_dash`) | 5 | **Different output contracts** (filing convention vs generic 2-decimals vs compact `$1.2B`). No action; the insights service reuses `format_fact_value`. |
| `classify_concept` / `humanize_concept` | 1 module | Not duplicated (single home in `financials_view_service`). No action. |
| SEC URL construction | 1 module (`filing_service.build_sec_urls`) | Not duplicated. No action. |

## Executed this session

Phase D (duplication elimination):

1. `verdict_color` + `confidence_color` → `cli/formatters.py` (9 method
   commands updated; `dcf.py` keeps its DCF-specific verdict map, which is a
   different vocabulary). Commit `5dd822a`.
2. `SOURCE_LABELS` → `backend/services/narrative_extractor.py` (updated
   `ui_adapter` and `cli/commands/filing_section.py`). Commit `d2fa15e`.

Phase E (file splits, pure moves — tests unchanged):

1. `financial_database_repository.py` 2174 → 1873 lines; extracted the
   concept-mapping block to `backend/repositories/fdb_concept_mapping.py`
   (322 lines); the services import from the new module, the repository
   keeps the used names. Commit `06ececb`.
2. `refresh_service.py` 954 → 711 lines; extracted `FdbGateway` to
   `backend/services/fdb_gateway.py` (259 lines); re-exported through the
   original module (tests import it from there). Commit `2e2bd82`.

## Remaining split candidates (future)

- `ui_adapter.py` (921): the portfolio block (`PortfolioView` + actions,
  ~400 lines) can move to `portfolio_adapter.py`; it shares `DASH` and
  `fmt_or_dash` with the kept part, so first extract those to a small
  `ui_format.py` to avoid an import cycle, then split.
- The repository class (1873) needs mixin-style splits (lookup /
  normalization / reads); single-class files (`price_service`, `dcf`,
  methodology classes) need concern-based mixins.
- `backend/config/settings.py` vs `backend/core/config.py` overlap
  (DEFAULT_* constants) — not a pure move (different APIs); consolidate
  deliberately in a future session.
