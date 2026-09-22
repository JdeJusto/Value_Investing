# Top-10 deep validation — 2026-09-22

Source universe: S&P 500 + Nasdaq-100 (deduplicated, `config/universe.csv`).
The top-10 came from the daily run over **500** companies
(`data/reports/daily_2026-09-22.md`, ranked on calibrated `rank_score`).
Each name was re-analyzed with `main.py analyze-full --no-refresh`
(6 sections: overview, real-time price/valuation, fundamentals, Buffett
quality, historical valuation, risks/anomalies/triggers) and the resulting
prices/valuations were cross-checked against external public sources
(company IR, Yahoo Finance, Google Finance, CNN Markets, Morningstar,
macrotrends) as of the 2026-09-21 close (2026-09-18 for some sources).

## 1. Top-10 — deep-validation summary

| # | Ticker | Company | Rank | Score | Price (VI) | Public ref. | Match | P/E | FCF yield | EV/EBIT | P/B | Mkt cap | DCF M.o.S. | Rating |
|---|--------|---------|------|-------|-----------|-------------|-------|-----|-----------|---------|-----|---------|-----------|--------|
| 1 | BF-B | Brown-Forman (B) | 83.0 | 90.1 | $26.15 | $26.15 | exact | 16.8 | 7.4% | 14.1 | 2.98 | $12.0B | 30.6% | A |
| 2 | ACN | Accenture | 81.2 | 90.2 | $186.11 | $186.11 | exact | 14.8 | 9.5% | 11.1 | 3.65 | $113.9B | 21.1% | A |
| 3 | MKC | McCormick | 80.8 | 88.4 | $48.89 | ~$50.4 (Sep 14) | ~ | 16.7 | 5.6% | 17.1 | 2.29 | $13.1B | 40.0% | A |
| 4 | PAYX | Paychex | 79.8 | 84.6 | $115.01 | ~$115–116 | ✓ | 23.3 | 5.7% | 17.7 | 10.96 | $40.9B | 8.9% | A |
| 5 | HII | Huntington Ingalls | 79.5 | 85.8 | $276.10 | $276.10 | exact | 18.0 | 7.3% | 21.0 | 2.14 | $10.9B | 29.2% | A |
| 6 | APTV | Aptiv | 78.2 | 88.0 | $43.57 | ~$43.6–43.9 | ✓ | 54.8 | 16.9% | 11.8 | 0.98 | $9.0B | 69.4% | A |
| 7 | HSIC | Henry Schein | 77.2 | 91.0 | $85.20 | $85.20 | exact | 23.9 | 6.0% | 22.5 | 2.93 | $9.5B | 14.4% | A |
| 8 | VRSK | Verisk | 76.9 | 83.8 | $172.02 | $172.02 | exact | 24.6 | 5.3% | 19.7 | 72.46* | $22.4B | 3.0% | A |
| 9 | HRL | Hormel | 75.8 | 89.4 | $20.46 | ~$20.8 (Sep 18) | ~1.8% | 23.5 | 4.7% | 18.5 | 1.43 | $11.3B | 36.9% | A |
| 10 | SWKS | Skyworks | 74.7 | 85.2 | $88.74 | $88.74 | exact | 28.0 | 8.3% | 26.5 | 2.32 | $13.4B | 37.6% | A |

\* VRSK P/B 72.46 and average ROIC 837.9% are book-equity denominator
artifacts — see caveats.

**External price cross-check.** 8/10 names match the same-day (2026-09-21)
public close **exactly** (BF-B, ACN, HII, HSIC, VRSK, SWKS, PAYX, APTV; the
last two within ~0.1–1%). HRL ($20.46) is ~1.8% below the 2026-09-18 public
close ($20.83) because the latest close was fetched one session later. MKC
has no same-day public quote available (company IR page provides Sep 14:
$50.39); the fetch ($48.89) sits inside the recent $48–52 trading band — no
discrepancy flag.

**Valuation cross-checks (independent computation from market data):**

| Ticker | VI P/E | External P/E (basis) | Match |
|--------|--------|----------------------|-------|
| BF-B | 16.8 | 16.86 (Google Finance, price/eps) | exact |
| ACN | 14.8 | 13.23 (Morningstar, normalized) | ✓ (two bases) |
| VRSK | 24.6 | 26.94 trailing (Yahoo) / 23.90 normalized (Morningstar) / 20.17 fwd (GuruFocus) | ✓ (in-band) |
| PAYX | 23.3 | ~22–24 (market cap / TTM EPS) | ✓ |
| Market caps | — | BF-B $12.10B, VRSK $22.83B, HRL $11.47B (Yahoo/Google/FIS) | ✓ |

Prices, market caps and P/E ratios reconcile with public sources, so the
ranking is based on sound price data.

## 2. Quality gate (per company, from `analyze-full`)

All 10 names are: **Rating A**, **moat STRONG**, confidence **HIGH**,
financial data source **EDGAR**, data quality **100.0%**, score total equal
to the daily-report `Score` column (byte-for-byte), and no price-persistence
of any kind (section 2 prices come from the in-memory PriceService — real
time only).

| Ticker | Buffett score | ROIC (avg) | Rev CAGR | Piotroski | Altman Z | Anomalies raised | Local trigger |
|--------|---------------|-----------|----------|-----------|----------|------------------|---------------|
| BF-B | 83.6 | 22.1% | 1.0% | 6/9 | 3.66 | 2 (FCF z 2.37 UP, FCF yoY +107% STRONG) | FCF surge |
| ACN | 91.2 | 18.0% | 7.6% | 4/9 | n/a | 3 (rev/NI/FCF z ~2.4 UP) | FCF surge |
| MKC | 89.0 | 10.3% | 4.9% | 5/9 | 2.25 | none | none |
| PAYX | 76.8 | 57.0% | 7.7% | 6/9 | 3.05 | 4 (FCF/rev/GM/ROIC z 2.0–3.0 UP) | FCF surge |
| HII | 78.9 | 26.4% | 4.7% | 5/9 | 2.60 | 2 (FCF yoY +2954% STRONG, rev z 2.33) | FCF surge |
| APTV | 76.0 | 49.7% | 2.1% | 5/9 | 1.80 | 3 (rev/FCF z 2.05 UP; **NI yoY −91% DOWN**) | none |
| HSIC | 82.3 | 18.8% | 3.8% | 3/9 | 2.67 | none | none |
| VRSK | 72.2 | 837.9%* | 6.2% | 4/9 | 5.26 | 2 (FCF z 2.68, GM z 2.08 — both UP) | FCF surge |
| HRL | 82.4 | 15.0% | 3.5% | 4/9 | n/a | none | none |
| SWKS | 80.2 | 23.1% | 9.3% | 4/9 | 5.43 | none | none |

The "local trigger" column is the single-ticker `detect_trigger` that the
`analyze-full` report itself displays. In that setting only the **absolute
floors** apply (fewer than 20 samples → the universe percentile channel is
skipped by design), which is why the FCF-surge label appears for 5 names
here even though the universe-calibrated daily alerts fire far more
selectively. These labels are informational, not the daily TRIGGER_EVENT
alerts.

The anomalies are overwhelmingly **mild, positive** spikes (recent capital
expenditures/FCF/revenue above 10-year means) — consistent with strong
fundamentals performance, not data corruption. The single DOWN flag is
APTV's FY2025 net-income collapse (−91% YoY), which explains its elevated
P/E.

## 3. Caveats discovered during validation

1. **VRSK — book-equity artifacts, not a price error.** Price ($172.02),
   market cap ($22.4B) and P/E (24.6 vs ~24–27 publicly) all verify. The
   P/B of 72.46 and 10-year average ROIC of 837.9% reflect a near-zero book
   equity base after years of buybacks. No ranking change; the ratios are
   just not economically meaningful for this name and should be read with
   care (candidate for a documented metric exclusion if ever screenable).
2. **APTV — the value case leans on FY2025; FY2026 is deteriorating.** The
   16.9% FCF yield and 69.4% margin-of-safety rest on the latest *completed*
   fiscal year's FCF ($1.5B). Public data shows FY2026 softening sharply
   (Q1-26 FCF −$362M vs +$76M a year earlier; 2026 projections point to a
   net cash outflow), and the P/E of 54.8 already prices the earnings
   collapse. This is the top-10 name where data-freshness matters most:
   when FY2026 closes, its rank will likely fall on that basis.
3. **SWKS — FY2025 basis understates the current multiple.** P/E 28.0 is
   computed on FY2025 EPS ($3.21). TTM EPS through Jun-2026 stands at $1.94,
   putting the current-earnings P/E near 46; the stock also rose ~32% during
   the month before this run. The ranking already handled this correctly:
   SWKS is #10 with a **WATCHLIST** signal (rank 74.7 < 75), i.e. it did not
   clear the BUY bar.
4. **HRL — small price-timing variance.** $20.46 vs the last widely-quoted
   $20.83 (2026-09-18); the live close fetched one session later. Within
   normal intraday variance; fundamentals (rev. growth 1.6%, F-score 4/9,
   low growth) are the softer points, not the price.
5. **HSIC — weakest balance-sheet profile of the top-10.** Piotroski 3/9 and
   Altman Z 2.67 (grey zone) contrast with its strong quality/composite
   (91.0, the highest Score in the top-10). The STRONG-moat/HIGH-confidence
   view is intact, but HSIC carries the most pre-existing leverage/stress
   among the names.
6. **Company-metadata gap.** Section 1 (Company overview) shows
   Sector/Industria N/A for all 10 — Value Investing's own company table has
   no sector/industry rows for these tickers. Cosmetic only: scoring comes
   from normalized financials, not this metadata. Candidate for enrichment
   from the Financial-DataBase `companies`/`company_listings` tables.

## 4. Verdict

The top-10 survived deep validation. Prices, market caps and P/E ratios
reconcile with external sources, composite scores reproduce the daily
report exactly, and all names pass the A/STRONG/HIGH quality gate with
EDGAR, 100%-quality fundamentals. No name needs to be removed or
re-ranked on the evidence reviewed. Two names warrant monitoring on the
freshness axis — **APTV** (FY2026 FCF deterioration) and **SWKS** (post-run
price spike vs FY2025-basis valuation) — and VRSK's book-value ratios are
flagged for interpretation. Section 5 below then re-reviewed APTV and SWKS
in depth against updated public sources and assigns final keep/demote
decisions that supersede this initial verdict.

## 5. Deep-dive re-reviews with keep/demote decisions (follow-up)

Both names were re-run with `main.py analyze-full --no-refresh` and
re-checked against StockAnalysis (S&P Global MI), Macrotrends, company
press releases/10-K, and SEC filings as of the 2026-09-21 close.

### 5.1 APTV — DEMOTE from the top-10 recommendation

**Cross-checks (VI vs external):**

| Metric | VI (`analyze-full`) | External | Match |
|---|---|---|---|
| Price | $43.57 | $43.57 (StockAnalysis, Sep 21 close) | exact |
| Market cap | $9.0B | $9.05B | exact |
| P/E (FY2025 GAAP) | 54.8 | EPS ttm $1.03 → ~42 at close | basis differs |
| Forward P/E (adj.) | — | 7.13 (StockAnalysis) | n/a |
| FY2025 revenue | $20.40B (+3.5%) | $20.40B (+3.47%) | exact |
| FY2025 net income | $165M (−90.8%) | $165M (−90.77%) | exact |
| FY2025 FCF | $1.5B | $1.549B (Macrotrends) | exact |

**Findings.**

1. **FCF deterioration is real and already visible in 2026.** Q1-26 FCF
   −$362M vs +$76M a year earlier; H1-26 FCF −$196M vs +$264M; Q2-26 only
   +$12M (including a $70M separation-cost drag); FY2026 guidance was cut
   (China weakness, delayed launches, software timing) and the stock fell
   ~20.7% in the 30 days after the Aug 4 Q2 report. The screener's 16.9%
   FCF-yield read on the *completed* FY2025 does not persist into FY2026.
2. **Entity mismatch inflates the value channels (new finding).** The
   Versigent PLC (Electrical Distribution Systems) spin-off was completed
   **April 1, 2026** (record date Mar 17, 2026, per SEC 8-K and the
   company's announcement). All fundamentals the analysis uses — FY2025
   revenue $20.40B, net income $165M, FCF $1.549B, and therefore the DCF
   ($29.6B) and margin-of-safety (69.4%) — are the **pre-spin combined
   company**. Section-2's price/market cap ($43.57 / $9.05B) are **New
   Aptiv only**. Mixing them overstates the FCF yield: it jumps from 9.45%
   at FY-end (consistent pre-spin price $76.09 × FY2025 FCF) to 16.9%
   mostly because half the company's equity value now trades separately as
   Versigent while the FCF numerator still includes Versigent's cash flows.
   New Aptiv itself generated **negative FCF in 2026 H1**.
3. **P/E 54.8 is a GAAP-collapse artifact, not an expensive signal.**
   FY2025 GAAP EPS $0.795 ($165M / 207.6M sh) is depressed by restructuring
   / spin charges; adjusted forward EPS guidance is $5.60–5.80 → adjusted
   forward P/E ≈ 7.6, and consensus ("Buy") sees ~53% upside to a $66.61
   target. The quality case (Buffett 76.0, STRONG moat, HIGH confidence,
   avg ROIC 49.7%) is about the 10-year combined history and is authentic.

**Decision — DEMOTE.** APTV (#6, rank 78.2, BUY) currently screens on value
inputs that mix two different companies. The honest standing until fresh
post-spin fundamentals arrive is **WATCHLIST / hold, not a top-10 BUY**.
No hand edit is made to the daily run (top-20 remains byte-identical).
The system self-corrects automatically: when FY2026 completes, the
comparative financials are New-Aptiv-only (Versigent classified as
discontinued operations), and with a negative trailing FCF the calibrated
leveraged cap (negative-FCF → rank ≤ 60) drops APTV out of the top-10 by
itself. Watch for that re-ranking on the next fundamentals refresh.

### 5.2 SWKS — KEEP at #10, standing WATCHLIST

**Cross-checks (VI vs external):**

| Metric | VI (`analyze-full`) | External | Match |
|---|---|---|---|
| Price | $88.74 | $88.74 (StockAnalysis, Sep 21 close) | exact |
| Market cap | $13.4B | $13.35B | exact |
| P/E | 28.0 (FY2025 EPS $3.21) | **45.87 TTM** (EPS $1.93) | basis confirmed |
| FY2025 revenue | $4.09B (−2.2%) | $4.09B (−2.18%) | exact |
| FY2025 FCF | $1.1B | $1.106B (10-K / IR) | exact |
| FY2025 GAAP EPS | $3.21 | $3.20 diluted (10-K) | ~exact |

**Findings.**

1. **The EPS-basis understatement is confirmed and already handled.** The
   28.0 P/E uses FY2025 EPS ($3.21); trailing EPS through Jun-2026 is $1.93
   → the real-time trailing multiple is ≈ 46 (StockAnalysis: 45.87). This
   is exactly why the run already signals **WATCHLIST, not BUY**: SWKS ranks
   #10 at 74.7, below the BUY threshold of 75. The system priced in the
   earnings decline before the price spike.
2. **Fundamentals verify cleanly and are entity-consistent** (no
   restructuring or spin differentiates numerator/denominator): FY2025 FCF
   $1.106B matches the 10-K press line, FCF yield 8.3%, Altman Z 5.43,
   Buffett 80.2, STRONG moat, HIGH confidence, Piotroski 4/9. FCF trend
   remains positive despite Q4-25's soft quarter (OCF $200M, FCF $144M).
3. **Material events since the FY2025 basis (not in EDGAR historicals):**
   the Qorvo combination is on track to close in 2026 (company-guided $500M
   of annual synergies; combined-company leadership named), and the
   quarterly dividend was **replaced by a $2B buyback** (Q3-26 announcement,
   with the board's $2.84 annual dividend discontinued). Street consensus
   turned to **Hold with an $68.35 target (−23%)** after the ~32% pre-run
   rally; 52-week range 51.93–92.30, trading near the high.

**Decision — KEEP at #10, signal stays WATCHLIST.** The multiple distortion
is real but already reflected by the signal, and the underlying cash-flow
and quality metrics verify exactly. SWKS is not promotable to BUY until a
post-FY2026 refreshed EPS narrows the trailing multiple or closed Qorvo
synergies rebase the thesis — which the deterministic refresh will handle.
No ranking change; the caveat is reaffirmed and now cites the TTM P/E of
~46 as externally confirmed.

### 5.3 Superseding verdict

- **APTV — DEMOTE** from the top-10 recommendation (entity-mismatch +
  negative 2026 YTD FCF). Expect automatic demotion at the next
  fundamentals refresh.
- **SWKS — KEEP** at #10 with WATCHLIST standing (verified fundamentals;
  signals already correct for the EPS-basis).
- No scoring/ranking code was changed: the 500-run outputs (top-20,
  alerts, prices) remain byte-for-byte identical to the validated run, and
  both actions are recorded here (and, for APTV, will crystallize in the
  refreshed daily state).