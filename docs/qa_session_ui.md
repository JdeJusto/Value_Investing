# QA session — UI walkthrough (2026-09-30)

AppTest, headless, real data (empty portfolio for the render pass, the
3-position fixture for the portfolio flow). No exceptions anywhere.

## Pages render (C2)

| Page | Status | Widgets rendered |
| --- | --- | --- |
| 01_home | OK | 2 dataframes (top opportunities + recent alerts from the latest report), 1 info (empty portfolio) |
| 02_analysis | OK | 1 button (Analyze), 1 info (prompt) |
| 03_screener | OK | 1 button (Run), filter panel |
| 04_portfolio | OK | 1 button (form submit), 2 infos (empty state) |
| 05_reports | OK | report list + preview + download |

## Primary flows (C3)

- **Home**: portfolio summary (empty state message), top opportunities and
  recent alerts render from `data/reports/daily_2026-09-29.md`. OK.
- **Analysis (KO)**: 5 tabs (Overview / Methodologies / DCF / Historical /
  Raw), **6 methodology rows**, 10 dataframes, 26 metrics, 8 expanders,
  DCF variant caption present. No exceptions.
- **Portfolio (3-position fixture)**: positions table + 3× Exit/Remove +
  "Fetch current prices" + add form (Acciones/Precio/Señal) all render.
- **Reports**: newest report listed first and previewed inline.

## UX issues observed

1. **Screener estimate caption rounds to "~0 min"** for small caps
   (`~0.6 s/ticker → ~0 min para 50 tickers`). Should read "~30 s" or
   "<1 min". → fixed in Phase G.
2. **Screener run took 91.8s for 50 tickers** (~1.8 s/ticker including
   the Yahoo snapshot prefetch and the methodology enrichment) — the
   caption estimate (0.6 s/ticker) understates the real cost. Update the
   estimate text to reflect ~1.5-2 s/ticker. → fixed in Phase G.
3. Filter panel starts collapsed (by design; the task asked for it).
4. Home with an empty portfolio shows the opportunities/alerts but no
   metric row — acceptable empty state.
5. Yahoo transient warnings appear in the server log (DNSError /
   ConnectionError "continuing without crumb") but never reach the UI.
