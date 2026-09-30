# QA session summary (2026-09-30)

## Scope

- **Tickers tested**: AAPL, MSFT (cross-checks), KO, JNJ (universe),
  XOM, F, GM (planned), JPM, WFC, USB, NVDA, TSLA, SHOP (planned),
  PLD, CROX/WING (small caps), OYSE (SPAC), TSM (ADR), RBRK (recent
  IPO), ZZZZ (unknown).
- **Commands run**: 33 CLI commands (Phase A) + 6 coherence commands
  (Phase B) + UI AppTest flows (Phase C/D) + portfolio/workflow E2E
  (Phase E) + edge cases and cross-checks (Phase F) ≈ **50 executions**.
- **Docs**: `qa_session_cli.md`, `qa_session_coherence.md`,
  `qa_session_ui.md`, `qa_session_screener.md`, `qa_session_workflow.md`,
  `qa_session_data_quality.md`.

## Bugs found and fixed

| # | Severity | Bug | Fix |
| --- | --- | --- | --- |
| 1 | P0 | `analyze-buffett-classic` rejected `--no-refresh` (exit 2) while the other five `analyze-*` commands accept it | commit `da54066` + parametrized CLI regression test |
| 2 | P2 | Screener estimate caption rounded to "~0 min" (real 91.8 s / 50 tickers) | commit `e4a6a34` (~1.8 s/ticker, seconds under 2 min) |
| 3 | P2 | Screener accepted min > max market cap silently (empty results) | commit `e4a6a34` (`validate_screener_range` + test) |

No other crashes or failures: 30/33 Phase-A commands exited 0 (the three
exit-2 were bug #1), every UI page and flow rendered without exceptions,
the portfolio cycle and the daily workflow completed cleanly.

## Improvements applied

- The two screener fixes above (both <30 lines with tests).
- QA docs created (six files).

## Regressions on the test suite

None: **1247 passed / 1 skipped** (1240 before the session + 7 new
tests: 6 CLI flag tests + 1 range validator). `ruff check .` → 0 errors.
`prices` table unchanged (152) across every flow, including the UI
refresh/save (verified on a copy) and the real workflow run.

## Overall health assessment

**~92% healthy.** Evidence:

- CLI: all commands work; one flag inconsistency (fixed). Slow commands
  are first-call price warm-ups, not defects (historical-valuation 37 s).
- Methodologies: family coherence holds; the only unclear case is the
  generic disagreement text on non-value/quality splits (XOM).
- DCF: 4 variants verified on real data; JPM/WFC/USB stable after the
  preferred-dividend fix; PLD REIT undervalued, AAPL/NVDA overvalued.
- UI: 5 pages, all flows, no Arrow/dtype issues; screener semantics
  verified (warning on capped verdict filters, CSV, 12 rows on a real
  filtered run).
- Data: exact EDGAR match on the AAPL spot check; core concept coverage
  high for companies with facts; the remaining gap is unmapped companies.
- Workflow: real run (limit 20) in 35 s, report with all sections, no
  prices persisted.

The 8% gap is: two P1 polish items, four P2 calibration/UX items, and
unmapped-universe coverage — all in `docs/backlog.md`.
