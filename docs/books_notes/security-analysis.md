> **Methodology:** `graham_dodd`
> **Reference:** Security Analysis (Graham & Dodd, 1934; Spanish ed.)
> **Availability:** full text extracted; the curated notes below are the
> versioned source of truth. Raw text lives in the gitignored `_raw/`.
> **src: /home/caudillo/Descargas/Security-Analysis-en-espanol.pdf**

# Security Analysis — Benjamin Graham & David Dodd

## 1. Bibliographic record
- **Title:** Security Analysis: Principles and Technique
- **Author(s):** Benjamin Graham & David Dodd
- **Year of first edition:** 1934
- **Edition analyzed:** Edición en español (distribuida por Online ROMA), 1.097 páginas, que incluye el texto clásico más comentarios contemporáneos (Roger Lowenstein, Warren Buffett, y otros)
- **Total pages:** 1.097
- **Language:** Spanish
- **Slug:** security_analysis_graham_dodd

## 2. Core investment philosophy

Graham and Dodd's thesis is that **securities should be analyzed as businesses, and bought only when the price is below the intrinsic value by a margin wide enough to absorb error**. They open by defining intrinsic value as "ese valor que está determinado por los hechos" (p. 89) — not by the market's opinion — and they insist that "la inversión no es, por naturaleza, una ciencia exacta" (p. 101): like law and medicine, analysis is indispensable even though skill and luck both matter.

What makes a good investment is **the relationship between price and value**, not the quality of the business alone. The "margin of safety" is the entire mechanism: "un espacio para el error, la mala suerte o… lo imprevisible" (p. 5). They are explicit that the margin exists because the future cannot be predicted: "Como el futuro es un libro cerrado, él [el inversor] necesita un margen de seguridad" (p. 101).

What they reject: the "new era" idea that a stock's attractiveness is independent of its price — "la noción de que el atractivo de unas acciones ordinarias es totalmente independiente de su precio parece increíblemente absurda" (p. 101); buying at 35x maximum earnings instead of 10x average earnings; and the belief that a small statistical edge is enough. Their LTCM example is devastating: "las probabilidades estaban a su favor" in every trade, yet leverage wiped the fund out — "un componente especulativo" (p. 101).

## 3. Universe of applicability
- **Company types:** all listed companies, but the method is most powerful for "empresas secundarias" — "las más o menos miles de las llamadas «empresas secundarias» deberían ofrecer, al menos, unas cuantas auténticas oportunidades de inversión bajo cualquier condición, excepto quizás en pleno apogeo de un mercado al alza" (p. 101).
- **Markets:** written for the US market of the 1920s–30s; the principles are market-agnostic but the examples are US rails, industrials and utilities.
- **Time horizon:** long term; the investor should buy "cuando los especuladores, agobiados o desanimados, están vendiendo" (p. 101).
- **Best conditions:** depressed markets and depressed individual companies — "el inversor ha de esperar períodos de negocio y niveles de mercado deprimidos para comprar acciones ordinarias representativas" (p. 101).
- **Worst conditions:** euphoric markets, where "criterios de selección lo bastante restrictivos" eliminate almost everything (p. 113).

## 4. Key metrics (EXHAUSTIVE table)

| Metric name | Formula | Buy threshold | Avoid threshold | Page | Notes |
|---|---|---|---|---|---|
| Net working capital (NWC) test | Price < 2/3 × (current assets − total liabilities) | below 2/3 of NWC | above 2/3 of NWC | 5 | "el clásico test de «capital circulante neto»"; "Muchas acciones se amoldaron a este criterio durante los años de la Gran Depresión" |
| Fixed charge coverage (railroad bonds) | Earnings ÷ fixed charges | ≥ 1,5× in 5 of the last 6 years (incl. the last) | below 1,5× | 230 | "la empresa debe haber ganado sus cargos fijos 1,5 veces en cinco de los seis años inmediatamente precedentes" |
| Fixed charge coverage (other bonds) | Earnings ÷ fixed charges | ≥ 1,5× in the last year and 5 of the 6 preceding | below | 230 | "deberán ganarse tanto en el último año como en cinco de los seis precedentes" |
| Dividend record (bonds) | Uninterrupted dividends | required, no substitution allowed | any interruption | 230 | "los requisitos en cuanto a pago de dividendos son aparentemente absolutos" |
| Size (gas/electric utilities) | Total assets | ≥ $1M (gas), ≥ $5M (electric) | below | — | "no ha de ser inferior a 1.000.000 de dólares para las compañías de gas y electricidad, y no inferior a 5.000.000 de dólares en el caso de" |
| Earnings yield vs bond yield | Earnings yield ÷ bond yield | ≥ 1,5× (reconstructed from prose) | below | — | The classic "earnings yield should be at least twice the bond yield" rule appears in later chapters; here the principle is stated qualitatively |
| P/E ceiling (pre-boom norm) | Price ÷ average earnings | ≤ 10× average earnings | 35× maximum earnings | 101 | "a 35 veces sus beneficios máximos declarados, en vez de a 10 veces sus beneficios medios —que era el criterio pre-boom—" |
| Margin of safety | Intrinsic value − market price | as wide as possible | any narrow or negative | 5, 101 | "un espacio para el error, la mala suerte o… lo imprevisible" |
| Intrinsic value | "determinado por los hechos" | price below intrinsic value | price above | 89 | "ese valor que está determinado por los hechos" |
| Cash flow (modern commentary) | Free cash flow (cash flow after capex) | high and predictable | low or volatile | 549 | "tendemos a centrarnos en el cash flow (flujo de caja) tras los gastos de capital (flujo de caja de libre disposición), en lugar de los beneficios" |

## 5. Decision rules (if-then)

- **IF** a stock trades below 2/3 of its net working capital → **THEN** it passes the classic bargain test. [EXPLICIT, p. 5]
- **IF** the investor waits for a market rise before buying → **THEN** "se opone básicamente a la naturaleza esencial de la inversión"; the patient investor "compra cuando los especuladores, agobiados o desanimados, están vendiendo". [EXPLICIT, p. 101]
- **IF** a bond's fixed charges are covered ≥ 1,5× in 5 of 6 years → **THEN** it meets the railroad-bond standard. [EXPLICIT, p. 230]
- **IF** a company is a "secondary" company → **THEN** it should offer "auténticas oportunidades de inversión bajo cualquier condición, excepto quizás en pleno apogeo de un mercado al alza". [EXPLICIT, p. 101]
- **IF** the investor relies on a small statistical edge with leverage → **THEN** he is speculating, not investing (the LTCM example). [EXPLICIT, p. 101]
- **IF** the investor cannot define intrinsic value → **THEN** he should not buy, because "un gran error pensar que el valor intrínseco es tan definido y determinable como el precio de mercado". [EXPLICIT, p. 101]
- **IF** the investor wants "criterios de inversión definitivos" → **THEN** he will be disappointed: "Nuestra búsqueda de criterios de inversión definitivos para el comprador de acciones ordinarias ha dado más advertencias que propuestas concretas". [EXPLICIT, p. 101]

## 6. Red flags (automatic rejection)

| Red flag | Description | Why it disqualifies | Page |
|---|---|---|---|
| Price above intrinsic value | No margin of safety | "un componente especulativo" | 101 |
| Buying at 35× maximum earnings | The "new era" criterion | The criterion of value itself changed, which is absurd | 101 |
| Leverage on a small edge | LTCM-style | "se arriesgó por encima de las pérdidas que podía permitirse" | 101 |
| Fixed charge coverage < 1,5× | Weak earnings vs interest | The bond standard is not met | 230 |
| Dividend interruption | Broken record | "los requisitos… son aparentemente absolutos" | 230 |
| Price > 2/3 of NWC | No longer a bargain | The classic test fails | 5 |
| "Permanent investment" myth | The belief that some bonds are immune to change | "la vieja idea de «inversiones permanentes»… sin duda, se ha esfumado para siempre" | 67 |

## 7. Position sizing and portfolio rules

- **Max position:** not specified numerically; the margin of safety is the sizing logic — the wider the margin, the more one can commit.
- **Min/max positions:** not specified.
- **Sector limits:** none explicit.
- **Entry:** "períodos de negocio y niveles de mercado deprimidos" (p. 101).
- **Exit:** when the price reaches intrinsic value, or when the facts change; the book gives no mechanical sell rule.
- **Rebalancing:** not addressed.
- **Cash policy:** not addressed; the emphasis is on being fully invested in qualifying securities.
- **Diversification:** the investor should hold a diversified list of qualifying stocks, but the book gives no count.

## 8. Assumptions and prerequisites

- Financial statements are **available and contain the facts** — though the authors warn that "no todos los elementos que inciden en el valor se plasman en los balances financieros de una empresa —los inventarios pueden volverse obsoletos y las cuentas por cobrar pueden ser irrecuperables—" (p. 5).
- The investor can **estimate intrinsic value within a range** — "la tasación es un arte, no una ciencia" (p. 5).
- The investor has the **patience** to wait for depressed periods and the **honesty** to admit mistakes (p. 101).
- The market will **eventually** recognize intrinsic value — "a la larga, el mercado" does (p. 101).
- The investor must **not be leveraged** beyond what losses he can bear (the LTCM lesson, p. 101).

## 9. Known limitations

- **No definitive equity criteria:** the authors admit their search "ha dado más advertencias que propuestas concretas" (p. 101) — the most honest admission in the book.
- **No sell discipline:** the margin of safety is an entry concept.
- **No portfolio construction or position sizing.**
- **Dated bond standards:** the 1,5× fixed charge coverage and the $1M/$5M size minimums reflect 1930s US railroads and utilities.
- **US-centric, Great-Depression-era examples.**
- **No treatment of growth valuation** — the book is about asset value and earnings power, not about valuing a franchise.
- **The NWC test is largely obsolete:** "Muchas acciones se amoldaron a este criterio durante los años de la Gran Depresión, pese a que ahora sean más bien escasas" (p. 5).

## 10. Overlap with existing modules

| Existing module | Overlap | What would be new |
|---|---|---|
| `backend/intelligence/buffett.py` | ~35% — both are Graham-derived value frameworks | The **NWC bargain test** (price < 2/3 NWC) as a distinct instrument; the **fixed-charge coverage** bond standard; the explicit "intrinsic value is a range, not a point" discipline |
| `backend/intelligence/moat.py` | ~15% | The margin of safety as the *bridge* between moat and price |
| `backend/analytics/scoring/` | ~25% — both compute valuation margins | The **earnings-yield vs bond-yield** comparison; the "35× max earnings vs 10× average" historical anchor |
| `backend/screener/` | ~30% — both filter | The NWC test and the coverage test as filters |

**Rough coverage: ~35%** of Security Analysis is already represented. The **net-working-capital bargain test and the fixed-charge coverage standard are the two most mechanically new instruments**, and both map directly onto existing filter criteria.

## 11. Distinguishing fingerprint

Security Analysis's unique contribution is the **margin of safety as a general principle applied to both bonds and stocks**, together with the insistence that **intrinsic value is a range determined by facts, not a point determined by the market**. Where *The Intelligent Investor* turns the principle into a checklist for the defensive investor, and *Common Stocks* turns it into a research method, Security Analysis turns it into a **discipline of scepticism**: "no todos los elementos que inciden en el valor se plasman en los balances" — the investor must always leave room for what the statements do not show. Its most quoted line is also its most honest: the search for definitive criteria "ha dado más advertencias que propuestas concretas".

## 12. Methodology family

**Primary: DEEP_VALUE**

Graham and Dodd are the founders of deep value: buy below intrinsic value, demand a margin of safety, and treat the market as a servant, not a master. The NWC test is the purest expression.

**Secondary: QUANTITATIVE_SYSTEMATIC** — the book is full of ratios, coverage tests and screening criteria that can be applied mechanically, and its modern commentators (Lowenstein, Buffett) emphasize the systematic side. But the authors themselves warn against pseudo-precision, so the quantitative side is deliberately subordinate to judgement.

## 13. Contradictions with common beliefs

| Common belief | This book's position | Reasoning |
|---|---|---|
| "Some bonds are permanently safe" | Rejected | "la vieja idea de «inversiones permanentes»… sin duda, se ha esfumado para siempre" (p. 67) |
| "A stock's attractiveness is independent of its price" | Rejected as "increíblemente absurda" | The margin of safety *is* the price (p. 101) |
| "Past growth predicts future growth" | Rejected | "la tasa de crecimiento durante el pasado, sorprendentemente, también" is not a predictor (p. 111) |
| "A small edge plus leverage is safe" | Rejected | LTCM had the edge in every trade and was wiped out (p. 101) |
| "Book value is what matters" | Rejected as a myth | "un mito muy extendido que Graham y Dodd solo confiaban en el valor contable" — intrinsic value is economic potential, not book (p. 101) |
| "Wait for the market to rise before buying" | Rejected | "¿cómo va a diferenciarse del especulador?" (p. 101) |
| "Diversification is always good" | Qualified | Diversification protects against ignorance; the analyst who knows the business needs less of it |

## 14. Sample rules in pseudo-code

```
net_working_capital_test:
if market_price < (2/3) * (current_assets - total_liabilities):
    return PASS   # "el clásico test de «capital circulante neto»"
else:
    return FAIL

fixed_charge_coverage:  # railroad bonds
if earnings >= 1.5 * fixed_charges in 5 of the last 6 years:
    return PASS
else:
    return FAIL

margin_of_safety:
if intrinsic_value_range_low > market_price:
    return PASS   # "un espacio para el error, la mala suerte"
else:
    return FAIL   # "un componente especulativo"

intrinsic_value_discipline:
if intrinsic_value_is_a_range_not_a_point:
    return PASS   # "la tasación es un arte, no una ciencia"
else:
    return FAIL   # "un gran error pensar que el valor intrínseco es tan definido
                  #  y determinable como el precio de mercado"

leverage_discipline:  # the LTCM lesson
if edge_is_small AND leverage_is_high:
    return FAIL   # "se arriesgó por encima de las pérdidas que podía permitirse"
else:
    return PASS
```
