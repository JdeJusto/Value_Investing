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

- `ui_adapter.py` is now 683 lines (general adapter + reports parsing +
  screener helpers); the reports/screener helpers could move to their own
  modules in a later pass.
- The repository facade is thin (160); single-class files
  (`price_service`, `dcf`, methodology classes) need concern-based mixins.
- `backend/config/settings.py` vs `backend/core/config.py` overlap
  (DEFAULT_* constants) — not a pure move (different APIs); consolidate
  deliberately in a future session.

## Execution plan (v0.10.2 session — splits via PRs)

Each split is a real PR (feature branch → PR → merge with CI green); the
refactor commits are pure moves (no behavior change, no test changes).

**Split 1 — `ui_adapter.py` (916 lines) → PR #1
(`refactor/split-ui-adapter`)**

1. Extract `DASH` + `fmt_or_dash` to `backend/services/ui_format.py`
   (pure move; `ui_adapter` imports them back, so existing importers keep
   working).
2. Move the portfolio block (`SECTOR_CONCENTRATION_THRESHOLD`,
   `PortfolioView`, `build_portfolio_view`, `PortfolioActionError`,
   `validate_new_position`, `add_position`, `exit_position`,
   `remove_position`, `refresh_portfolio_prices`, `save_portfolio_prices`)
   to `backend/services/portfolio_adapter.py`. `ui_adapter` re-exports the
   names pages/tests import, using the existing `# noqa: F401` pattern from
   `balance_sheet_parser.py`.
3. Add real coverage for the moved module (co-authored commit for Pair
   Extraordinaire).

Targets: `ui_adapter` < 500 lines, `portfolio_adapter` < 400,
`ui_format` < 100.

**Split 2 — `financial_database_repository.py` (1873) → PR #2
(`refactor/split-repository-mixins`)**

- New package `backend/repositories/fdb_mixins/`:
  - `helpers.py` — module-level pure helpers (`_as_date`,
    `_period_end_year`, `_cumulative_split_multiplier`).
  - `facts_mixin.py` — reads (`list_years`, `list_all_facts`,
    `get_by_year`, `list_all`, `get_best_available`, `has_data`,
    `get_normalized_financials`, `_list_years_uncached`,
    `_min_fiscal_year`, `_row_is_empty`, `_lookup_cache`).
  - `normalization_mixin.py` — `_normalize_financial_facts`,
    `_calculate_derived_fields`, `_build_normalized_financials`, `upsert*`,
    `delete_ticker`.
  - `shares_mixin.py` — shares + split ratios.
  - `fiscal_year_mixin.py` — fiscal year end / latest completed year.
  - `filings_mixin.py` — `list_filings`, `fundamentals_fingerprint`.
  - `lookups_mixin.py` — company id/name/sector + listings (`get_cik`,
    `has_active_listing`).
- `financial_database_repository.py` keeps the connection/cache core and
  becomes a facade inheriting all mixins; `_as_date` and
  `_cumulative_split_multiplier` stay importable from it (tests import
  them there).

Targets: facade < 400 lines, each mixin < 500.

**Cross-repo + Quickdraw**

- PR #3: one small, real improvement in Financial-DataBase (docs/typo or
  missing docstring) — skipped if no genuine improvement exists.
- Quickdraw: open a real issue (missing docstring), fix it, close it
  within 5 minutes.

- [x] PR #1: split ui_adapter
- [x] PR #2: split financial_database_repository
- [x] PR #3: FDB small contribution
- [x] Issue + close: Quickdraw

## Executed in v0.10.2 (via PRs)

- **PR #20** — `ui_adapter.py` 916 → 683: `ui_format.py` (DASH/fmt_or_dash,
  20 lines) and `portfolio_adapter.py` (250 lines) extracted; `ui_adapter`
  re-exports the moved names (`# noqa: F401` pattern). New coverage in
  `tests/unit/test_portfolio_adapter.py` (co-authored commit).
- **PR #21** — `financial_database_repository.py` 1873 → 160: per-concern
  mixins in `backend/repositories/fdb_mixins/` (facts 408, normalization
  470, shares 338, fiscal year 175, filings 130, lookups 209, helpers 73);
  the module keeps the connection/cache core and composes them. Pure move,
  tests unchanged.
- **PR #3 (Financial-DataBase)** — `financial-database --version` reported
  a hardcoded `0.3.0`; it now reads `__version__` and the
  release-consistency suite covers the CLI.
- **Issue #22** — docstrings for the alert notifier helpers (`lab`,
  `console_only`), fixed and closed in 5 seconds.
