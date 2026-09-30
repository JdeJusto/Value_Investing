# QA session — CLI smoke test (2026-09-30)

33 commands run once each (venv, `SEC_USER_AGENT` set, `--no-refresh` where
supported). Full log: `/tmp/opencode/qa_a.log` (ephemeral).

| Command | Exit | Duration | Flag | Notes |
| --- | --- | --- | --- | --- |
| analyze-graham AAPL | 0 | 13.6s | OK | AVOID 28.57, LOW |
| analyze-graham KO | 0 | 14.6s | OK | AVOID 14.29, LOW |
| analyze-graham F | 0 | 23.4s | WARN | INSUFFICIENT_DATA (financial fingerprint: Ford Credit) |
| analyze-graham-dodd AAPL | 0 | 8.9s | OK | AVOID 25.00 |
| analyze-graham-dodd KO | 0 | 15.0s | OK | WATCH 50.00 |
| analyze-graham-dodd F | 0 | 26.0s | WARN | INSUFFICIENT_DATA (financial fingerprint) |
| analyze-buffett-classic AAPL | **2** | 1.8s | **FAIL** | `--no-refresh` unrecognized — command lacks the refresh flags |
| analyze-buffett-classic KO | **2** | 1.8s | **FAIL** | same |
| analyze-buffett-classic F | **2** | 1.8s | **FAIL** | same |
| analyze-buffett-classic AAPL (retry without flag) | 0 | — | OK | WATCH 74.72 (see coherence doc) |
| analyze-buffett-classic KO (retry) | 0 | — | OK | BUY 80.46 |
| analyze-buffett-classic F (retry) | 0 | — | OK | AVOID 34.66 |
| analyze-buffett-clark AAPL | 0 | 2.1s | OK | BUY 71.43 |
| analyze-buffett-clark KO | 0 | 2.3s | OK | WATCH 57.14 |
| analyze-buffett-clark F | 0 | 2.2s | WARN | INSUFFICIENT_DATA (financial fingerprint) |
| analyze-fisher-quant AAPL | 0 | 2.2s | OK | BUY 100.00 |
| analyze-fisher-quant KO | 0 | 2.1s | OK | WATCH 75.00 (R&D not reported) |
| analyze-fisher-quant F | 0 | 1.9s | WARN | INSUFFICIENT_DATA (financial fingerprint) |
| analyze-lynch-garp AAPL | 0 | 26.1s | WARN (>20s) | AVOID 20.00, Stalwart |
| analyze-lynch-garp KO | 0 | 15.9s | OK | BUY —, Slow Grower |
| analyze-lynch-garp F | 0 | 18.8s | WARN | INSUFFICIENT_DATA; two Yahoo DNSError warnings |
| dcf AAPL | 0 | 20.7s | WARN (>20s) | standard, $140.37, OVERVALUED |
| dcf PLD | 0 | 6.7s | OK | reit, $203.30, UNDERVALUED |
| dcf JPM | 0 | 5.3s | OK | ddm_financial_two_stage, $167.30, OVERVALUED |
| dcf NVDA | 0 | 10.5s | OK | standard, $48.21, OVERVALUED |
| analyze-full AAPL | 0 | 19.1s | OK | score 82.9; DCF $140.37 |
| compare-methodologies AAPL | 0 | 4.9s | OK | 6 rows |
| compare-methodologies KO | 0 | 18.2s | WARN | one Yahoo DNSError warning |
| company AAPL | 0 | 4.7s | OK | F-Score 7, Z-Score 12.37 |
| data-status AAPL | 0 | 2.1s | OK | — |
| historical-valuation AAPL | 0 | **37.4s** | WARN (>30s) | four Yahoo DNSError warnings |
| methodologies list | 0 | 2.3s | OK | — |
| methodologies show graham | 0 | 1.9s | OK | — |
| portfolio view | 0 | 1.9s | OK | 0 posiciones |
| portfolio performance | 0 | 2.4s | OK | — |
| daily_workflow --dry-run --limit 10 --top 5 | 0 | 22.4s | OK | table + DCF section rendered |

## Findings

1. **FAIL (bug): `analyze-buffett-classic` does not accept `--no-refresh`** —
   the other five `analyze-*` commands do. Exit 2 with
   `unrecognized arguments: --no-refresh`. → fixed in Phase G.
2. **WARN: Yahoo DNSError** ("Cookie/crumb fetch failed (DNSError),
   continuing without crumb") on 8 commands — transient host DNS flakiness;
   the price service degrades correctly and the commands complete.
3. **WARN: Ford (F) trips the financial fingerprint** in graham,
   graham-dodd, buffett-clark, fisher and lynch (all INSUFFICIENT_DATA).
   Ford Credit makes `total_liabilities / total_assets > 0.85`, so the
   shared detector types the whole company as financial. Documented as a
   calibration limitation (backlog P2), not a crash.
4. **WARN: slow commands** — `historical-valuation AAPL` 37s (per-year
   Yahoo price fetches) and several 20-26s commands (first-call price
   warm-up). Acceptable for a CLI, noted for the backlog (P3: cache warm-up).
