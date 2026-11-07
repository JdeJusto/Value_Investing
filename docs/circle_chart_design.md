# Peer comparison radar (circle chart) — design

Status: implemented in v0.22.0.

The real-usage note asked for "algo como Simply Wall St: un círculo con las
categorías value, health, growth…". This is the **radar de peers** option
(Option A): the six scorecard dimensions of one company drawn on top of the
same six axes for its closest same-sector peers. It answers "how does this
company compare with the companies an investor would actually compare it
to?", which the single-company radar cannot.

Rejected alternatives:

- **Option B — concentric circles per dimension.** Prettier in isolation, but
  it does not support comparison: two companies cannot be overlaid and a
  "similar companies" search is impossible.
- **Option C — hybrid.** Radar + peer table is what ships; a separate circle
  packing chart adds no information over the radar, so it is not built.

## Selection rule

1. Build the subject's scorecard; read its `sector` (fallback: `industry`).
2. Ask Financial-DataBase for active listings in the same group, excluding the
   subject, ordered by latest `core_financials.total_assets` (a deterministic
   size proxy, no price/network access).
3. Order the candidates by market cap (USD) and build each scorecard, keeping
   the first **N = 5** with at least one scored dimension. Companies whose scorecard is `N/A` by design (banks,
   insurers, capital-markets firms, REITs) are skipped: their six axes carry no
   score, so they would draw an empty polygon.
4. If fewer than N qualify, draw the ones available. Zero peers is not an
   error: the tab shows the single-company radar and a caption.

The peer set is intentionally **not** persisted: it depends on the current
facts, and the scorecard is already cached per ticker in the UI.

## Chart

- One `Scatterpolar` trace per company, subject first.
- Subject: neon cyan, 2px, `toself` fill at low opacity.
- Peers: the synthwave accents (pink, gold, purple, mint, orange, lavender),
  1px, no fill.
- Axis range fixed 0–10, same as the scorecard radar.
- A dimension with no score stays `None`; the subject's polygon is not
  filled while it has a gap (missing is not zero).

## ASCII mockup

```text
 Peers · AAPL vs same-sector companies
 ┌───────────────────────────────────────────────┐
 │                    Growth                     │
 │                      10                       │
 │              8╱────────╲8                    │
 │   Management ╱   AAPL    ╲ Profitability      │
 │    / Moat   │  · MSFT    │                   │
 │   10 ───────┼───· NVDA ──┼──── 10            │
 │             │  · AVGO    │                   │
 │             ╲   · ACN    ╱                   │
 │  Shareholder ╲__________╱  Financial Health   │
 │   Returns           Valuation                 │
 └───────────────────────────────────────────────┘
 AAPL         Growth  Profit  Health  Value  Returns  Moat
 AAPL            7       9       7      2       8       7
 MSFT            8       9       8      3       8       6
 NVDA           10      10       9      1       6       8
 AVGO            9       8       6      3       5       7
 ACN             5       7       8      4       7       6
```

The shipped table is the same matrix rendered with `st.dataframe`
(rows = dimension labels, columns = tickers, plus a "Company" highlight).

## API

`backend/services/peer_comparison_service.py`

```python
PeerComparisonService(repository=None, scorecard_service=None, price_service=None)
  .get_peer_dimensions(ticker, n_peers=5)
      -> {"AAPL": {"growth": 7, ...}, "MSFT": {...}, ...}
```

Candidate ordering uses Yahoo market cap (USD, batched snapshot, never
persisted). `core_financials.total_assets` cannot order a cross-border sector
because it is reported in the filing currency (Sony in JPY, LG Display in
KRW), which would put them ahead of US mega caps.

- The subject is always the first key; peers follow in size order.
- Only scores (`int | None`) are returned; labels and formatting stay in the
  UI.
- Degradation: no scorecard, unknown sector/industry, database unavailable or
  no peers → `{}` or a one-entry dict, never an exception.

Repository support: `LookupsMixin.list_peer_tickers(sector=…, industry=…,
exclude=…, limit=…)`, one read-only query on `company_listings` + `companies`
+ the latest `core_financials.total_assets`.

## UI

`ui/pages/02_analysis.py` → `Peers` tab (after Scorecard):

- caption "Peer comparison · same sector · source: Financial-DataBase"
- radar (`ui/charts.py::peer_radar_figure`)
- matrix table with one row per dimension and one column per company
- caption with the resolved peer group and "N/A dimensions are gaps, not 0".

## Tests

- `get_peer_dimensions` returns N peers (fake repository + fake scorecards).
- same-sector only: the repository is asked with the subject's sector.
- N/A peers are skipped and do not consume a slot.
- fewer than N peers → the available ones.
- `peer_radar_figure` has one trace per company and the subject comes first.
- the Analysis page registers the Peers tab.

## Non-goals

- No circle packing, no similarity search by arbitrary dimension ranges (the
  "create your own circle" idea) — deferred to the scorecard backlog.
- No persistence of the peer set and no new price access.
