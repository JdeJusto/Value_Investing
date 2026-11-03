# Scorecard radar — diseño del dimension filter

> **Estado: SOLO DISEÑO.** Este documento propone tres opciones de "filtro de
> dimensiones del radar" para la pestaña Scorecard. No hay una sola línea de
> implementada: `ui/`, `backend/` y `tests/` están intactos en esta rama
> (`feat/radar-filter`). La implementación (C.2) solo empezará tras la
> aprobación humana de **una** opción de este documento.
>
> Todo lo marcado como "verificado" se ha leído del código con su referencia
> exacta (fichero:línea). Nada está supuesto.

---

## 1. Estado actual (verificado)

### 1.1 Componente del radar

| Pieza | Ubicación | Qué hace |
|---|---|---|
| `radar_data` | `ui/charts.py:19` | Devuelve `(labels, radii)` de las 6 dimensiones. Un score ausente queda `None`, **nunca 0** ("missing is not the same as bad", docstring literal). |
| `radar_missing` | `ui/charts.py:32` | Etiquetas de los ejes sin puntuar (los huecos). |
| `radar_figure` | `ui/charts.py:39` | Figura plotly `Scatterpolar` de 6 ejes, escala 0–10 (`RADAR_RANGE`, `ui/charts.py:16`). |
| `_scorecard_radar` | `ui/pages/02_analysis.py:692` | Render: `st.plotly_chart(figure, config={"displayModeBar": False})`; si plotly falla, cae a `st.bar_chart` con los mismos datos. Debajo, caption *"Not scored (insufficient data): …"* si hay huecos. |
| `_render_scorecard` | `ui/pages/02_analysis.py:624` | Orquestador: header → focus picker (`:647`) → radar (`:648`) → tarjetas (`:650-654`) → charts → descarga. |

**El radar es completamente estático.** Sin interacción: `displayModeBar`
desactivado, ningún `on_select`, ningún click. Siempre dibuja **los 6 ejes**
con un único polígono — el focus picker **no le llega nunca**: en
`_render_scorecard` el foco solo se usa en `:654`
(`expanded=focus == dimension["label"]`), mientras `_scorecard_radar(dimensions)`
recibe la lista completa sin argumento de foco.

### 1.2 Control de dimensiones hoy: el "focus picker"

`_scorecard_focus` — `ui/pages/02_analysis.py:677-689`:

- Widget: **`st.selectbox`** con label *"Focus a dimension (opens its rules)"*.
- Opciones: `["—", *labels]` — es decir, **sin foco ("—") + las 6
  dimensiones**. Es **single-select**.
- Default: **"—"** (índice 0 del `selectbox`; no hay `index=` explícito).
- Estado: **`st.session_state` vía `key=f"scorecard_focus_{ticker}"`** — una
  clave **por ticker**. No hay callback, no hay `st.session_state` extra, no
  hay cookie, no hay URL.
- Efecto real: **no toca el radar**. Devuelve la etiqueta elegida y
  `_render_scorecard` la usa únicamente para dejar **abierto el expander
  "Rules"** de esa tarjeta (`_scorecard_dimension`, `:835`, recibe
  `expanded=True`). El resto de tarjetas quedan plegadas.

Su propio docstring lo dice (`:678-681`):

> *"Picker that opens one dimension's rules (**radar axis-click
> fallback**). Streamlit's ``on_select`` axis-click is **deliberately not
> wired yet**; the documented fallback is this selector."*

O sea: el código documenta que el click en un eje del radar **no está
conectado a propósito** y que este selector es su sustituto — pero el
sustituto tampoco modifica el radar.

### 1.3 Las 6 dimensiones (nombres exactos, del código)

De `_DIMENSION_META` (`backend/services/scorecard_service.py:906-913`) con el
orden de los ejes por `DIMENSION_ORDER` (`backend/services/scorecard_service.py:73-80`):

| # | `key` | `label` (nombre exacto) | Pregunta |
|---|---|---|---|
| 1 | `growth` | **Growth** | Is the business getting bigger? |
| 2 | `profitability` | **Profitability** | Does it earn good returns on its money? |
| 3 | `financial_health` | **Financial Health** | Can it service its debts? |
| 4 | `valuation` | **Valuation** | Is the price reasonable? |
| 5 | `shareholder_returns` | **Shareholder Returns** | Does the owner get paid? |
| 6 | `management_moat` | **Management/Moat** | Will the returns last? |

(Ojo: en el orden real del radar, **Shareholder Returns va antes que
Management/Moat** — no al revés.)

### 1.4 Cómo se dibuja hoy un eje `—` (insufficient data)

Verificado en `radar_figure` (`ui/charts.py:39-74`):

1. `radii` lleva `None` en ese eje (`radar_data`, `ui/charts.py:28`).
2. `connectgaps=False` (`:54`) → la línea **se rompe** en el vértice `None`:
   el polígono no cruza el hueco.
3. `has_gap = any(radius is None …)` (`:48`) → **`fill=None` (`:55`): un
   solo eje sin puntuar elimina el relleno de TODO el polígono**. La silueta
   entera queda solo como contorno.
4. `radar_missing` + caption (`ui/pages/02_analysis.py:712-714`): bajo el
   radar aparece *"Not scored (insufficient data): <etiquetas>"*.

Es decir: el eje `—` **se dibuja** (la palabra queda en el eje angular) pero
el valor no, y — de paso — **la forma pierde su relleno completa**. Esta es
la parte visual que hoy ningún control permite mitigar.

### 1.5 Qué cubren los tests hoy

En `tests/unit/test_ui_scorecard_tab.py`:

| Test | Línea | Cubre |
|---|---|---|
| `test_radar_renders_as_a_plotly_chart` | `:322` | El radar sale como `st.plotly_chart`. |
| `test_radar_data_keeps_unscored_axes_as_gaps` | `:327` | `radar_data` conserva `None` y `radar_missing` devuelve `["Shareholder Returns"]`. |
| `test_radar_falls_back_when_plotly_is_unavailable` | `:338` | Fallback a `st.bar_chart`. |
| `test_focus_selector_lists_the_dimensions` | `:396` | **Solo** `focus.options == ["—", *_DIMENSION_LABELS]`. |

No hay ningún test de: persistencia del foco, efecto visual del foco en el
radar, cambio de foco al cambiar de ticker (no existe tal efecto), ni
interactividad del radar (no existe). `test_ui_pages.py` solo menciona
`ui/pages/02_analysis.py` en una lista de ficheros (`:31`).

### 1.6 Estado del header (para los mockups)

`_scorecard_header` (`ui/pages/02_analysis.py:799`) dibuja, verificado:
`**{ticker} · {company}**`, métricas **Price** y **Data quality**
(HIGH/MEDIUM/LOW, `_data_quality` `backend/services/scorecard_service.py`),
caption `{sector} · {industry}`, y el número grande del veredicto
**Overall** (etiquetas: `Strong`, `Mixed`, `Weak`, `Insufficient data` —
`_overall`, "a label, never a mastered number"). Las tarjetas
(`_scorecard_dimension`, `:835`) son `st.container(border=True)` con
`### label` + `## score/10` + `**verdict** · trend` + expander *"Rules"*. **No
son clicables hoy** (ningún `on_click` en el Scorecard).

---

## 2. Qué NO hace hoy (gap real, verificado)

El diseño original pedía *"interactive filters on the Scorecard tab — choose
which dimensions to display in the radar"*. Punto por punto:

| Capacidad pedida | ¿Existe? | Verificación |
|---|---|---|
| Elegir qué dimensiones se **muestran en el radar** | **No** | `_scorecard_radar` recibe siempre la lista completa (`:648`); ningún widget toca el radar. |
| Ocultar una dimensión del radar | **No** | No hay ningún mecanismo de ocultado en `ui/`. |
| Comparar 2+ dimensiones side by side / subconjuntos | **No** | Un único polígono de 6 ejes; el foco es single-select y solo abre reglas. |
| Resaltar la dimensión enfocada en el radar | **No** | El foco no llega al radar (`:654` vs `:648`). |
| Persistir la preferencia entre sesiones | **No** | Solo `session_state` con key por ticker; al recargar la pestaña se pierde. |
| Compartir una URL con el filtro aplicado | **No** | `st.query_params` **no se usa en ningún fichero de `ui/`** (grep vacío): no existe el patrón en esta UI. |
| Click en un eje del radar | **No** | Docstring del propio código: `on_select` "deliberately not wired yet" (`:680-681`). |

**Honestidad sobre el "gap de información": no lo hay.** Las 6 puntuaciones
están **siempre** visibles en las tarjetas de abajo, filtre o no el usuario.
El valor de un filtro es **visual/análítico** (forma de la silueta sobre un
subconjunto, quitar el eje `—` para recuperar el relleno, comparar empresas
con la misma forma parcial), no informativo. Decirlo claro antes de vender
una feature.

---

## 3. Pain points (hipótesis validadas leyendo el código)

1. **El picker parece no hacer nada** *(verificado)*. El usuario elige una
   dimensión y **el radar no cambia ni un píxel** (`:647-648`: el foco solo
   llega al expander de la tarjeta, `:654`). Lo único que ocurre — abrir
   "Rules" — sucede **debajo del radar**, fuera de la mirada. Un usuario que
   espera un filtro visual concluye que el control está roto.

2. **Un único eje `—` anula el relleno de toda la silueta** *(verificado:
   `ui/charts.py:48,55`)*. Con Shareholder Returns sin puntuar, el radar
   completo pasa de forma rellena a contorno suelto. El usuario no puede
   mitigarlo: no hay forma de quitar ese eje.

3. **Cambiar de ticker resetea el foco a "—"** *(verificado: key
   `scorecard_focus_{ticker}` + default índice 0)*. Para comparar las reglas
   de "Valuation" en AAPL y MSFT hay que reseleccionar en cada empresa. (Matiz
   verificado: volver al ticker anterior **sí** recupera su selección dentro
   de la misma sesión, porque `session_state` conserva la clave vieja. Se
   pierde al recargar la página.)

4. **No existe ningún filtro — ni siquiera uno tosco** *(verificado)*. Ni
   ocultar, ni subconjuntos, ni URL compartible. El radar es estático de
   nacimiento a render (`:692-714`). Cualquier "ver solo las 3 dimensiones de
   calidad" obliga a leer 3 tarjetas y a imaginarse la silueta.

---

## 4. Mockups

Datos de ejemplo usados en los tres (coherentes): Growth 9/10 ·
Profitability 10/10 · Financial Health 5/10 · Valuation 4/10 · Shareholder
Returns **—** (insufficient) · Management/Moat 7/10 · Overall `Mixed` ·
data quality `HIGH`. El `—` de Shareholder Returns está elegido a propósito:
es el caso del eje sin puntuar.

### Opción A — Focus single-select pulido (resalta el eje enfocado)

Mantiene el comportamiento de un solo foco y su efecto actual (abrir las
reglas), y le añade lo que le falta: **visibilidad**. El eje elegido se
resalta en el radar (segundo trace o vértice marcado) y el copy explica qué
hace. Además, la clave del widget pasa de `{ticker}` a una única
`scorecard_focus`, de modo que **el foco sobrevive al cambio de empresa**
(pain point 3).

```
┌─────────────────────────────────────────────────────────────────────┐
│ AAPL · Apple Inc.                                                   │
│ Price  $265.32            Data quality HIGH                         │
│ Technology · Consumer Electronics              ┌─────────────────┐  │
│                                                │      Mixed       │  │
│                                                │     Overall      │  │
│                                                └─────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  Focus: [Valuation ▾]    ← abre sus reglas Y resalta su eje          │
├─────────────────────────────────────────────────────────────────────┤
│                            Growth 9                                 │
│                              ▲                                      │
│                             ╱ ╲                                     │
│                 Mgmt 7     ╱   ╲     Profitability 10               │
│                           ╱  ●  ╲   (eje Valuation: vértice ● y     │
│        Shareholder —     ╱       ╲   trazo más grueso)               │
│                      ╱───────────╲                                  │
│              Valuation 4 ╲     ╱ Financial Health 5                  │
│                 (resaltado) ╲ ╱                                     │
│   Not scored (insufficient data): Shareholder Returns               │
├─────────────────────────────────────────────────────────────────────┤
│ Tarjetas (siempre las 6, inalteradas):                              │
│ ┌────────────────────┐ ┌────────────────────┐                        │
│ │ Growth         9/10│ │ Profitability 10/10│                        │
│ ├────────────────────┤ ├────────────────────┤                        │
│ │ Financial Health 5 │ │ Valuation      4/10│  ← Rules ABIERTO       │
│ │   [Rules ▾ abierto]│ │   [Rules ▸]        │                        │
│ ├────────────────────┤ ├────────────────────┤                        │
│ │ Shareholder R.   — │ │ Management/Moat 7/10│                       │
│ └────────────────────┘ └────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

- **Comportamiento**: selectbox único como hoy; cambia qué tarjeta tiene
  "Rules" abierto **y** qué eje aparece resaltado en el radar. Default:
  seguir con `"—"` (cambiarlo a "Profitability" alteraría el render inicial
  y barría el baseline visual `verify_theme` sin necesidad). Persistencia:
  key única (compartida entre tickers) dentro de la sesión.
- **Ejes `—` (obligatorio responder)**: los 6 se dibujan **siempre**; un eje
  `—` se dibuja exactamente como hoy (ruptura de línea, sin relleno, caption
  debajo). Enfocarlo lo resalta igualmente (el resaltado es sobre el eje, no
  sobre el valor). **Cero cambios en `radar_figure` salvo el parámetro
  opcional de resaltado.**
- **Ventaja**: coste mínimo, no cambia el layout, familiar.
- **Desventaja**: **no implementa el filtro pedido** (sigue sin poder ocultar
  ni ver un subconjunto).

### Opción B — Multi-select de dimensiones (filtro real del radar)

Un control nuevo decide qué ejes dibuja el radar; **las tarjetas siguen
mostrando las 6 siempre**. El focus picker se conserva intacto (es otra
preocupación: drilling de reglas vs. filtrado visual). Hay precedentes
nativos en esta UI: `st.multiselect` en `02_analysis.py:267,271,1003`,
`03_screener.py:80,85,108,109`, `06_consensus.py:128`; `st.checkbox` en
`balance_sheet.py:531,533`, `03_screener.py:110`.

```
┌─────────────────────────────────────────────────────────────────────┐
│ AAPL · Apple Inc.                                                   │
│ Price  $265.32            Data quality HIGH                         │
│ Technology · Consumer Electronics              ┌─────────────────┐  │
│                                                │      Mixed       │  │
│                                                │     Overall      │  │
│                                                └─────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  Radar dimensions:                                                  │
│   [x] Growth          [x] Financial Health    [ ] Shareholder Returns│
│   [x] Profitability   [x] Valuation                                  │
│   [x] Management/Moat                                                 │
│  5 of 6 shown — Shareholder Returns hidden (not scored)              │
│  Focus: [— ▾]   (selector actual, sin cambios)                       │
├─────────────────────────────────────────────────────────────────────┤
│                            Growth 9                                 │
│                              ▲                                      │
│                             ╱ ╲                                     │
│                 Mgmt 7     ╱   ╲     Profitability 10               │
│                           ╱     ╲                                   │
│                          ╱  ●●●  ╲  ← relleno RECUPERADO: sin el     │
│             Valuation 4 ╱───────╲ Financial Health 5    eje `—`,     │
│                        ╱         ╲                      has_gap=False│
│   (polígono cerrado con 5 ejes; caption "5 of 6 shown")             │
├─────────────────────────────────────────────────────────────────────┤
│ Tarjetas (siempre las 6, inalteradas):                              │
│ ┌────────────────────┐ ┌────────────────────┐                        │
│ │ Growth         9/10│ │ Profitability 10/10│                        │
│ ├────────────────────┤ ├────────────────────┤                        │
│ │ Financial Health 5 │ │ Valuation      4/10│                        │
│ ├────────────────────┤ ├────────────────────┤                        │
│ │ Shareholder R.   — │ │ Management/Moat 7/10│                       │
│ └────────────────────┘ └────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

- **Comportamiento**: `st.multiselect` (o fila de `st.checkbox`) con las 6
  dimensiones; el radar se dibuja con **la lista filtrada**. Filtro por
  sesión, compartido entre tickers (mismo subconjunto al cambiar de empresa —
  mata el pain point 3 para el radar). `radar_figure` **no necesita tocar
  signature**: la página le pasa la sublista (`radar_data`/`radar_missing` se
  calculan sobre la misma sublista, así que el caption es coherente).
- **Guard N ≥ 3**: con 3 activas, deshabilitar el un-check de las restantes
  (`disabled=len(active) <= 3`) — nunca se llega a un polígono degenerado.
  Con 3–6 ejes la polar siempre tiene forma.
- **Ejes `—` (obligatorio responder)**, política explícita:
  - **Marcado (default)** → se dibuja como hoy: ruptura de línea, sin
    relleno, caption *"Not scored…"*. **Default = las 6 marcadas → el render
    inicial es byte-idéntico al actual** (ninguna línea visual cambia hasta
    que el usuario filtra: baseline `verify_theme` intacto).
  - **Desmarcado** → el eje desaparece y `has_gap` se recalcula solo sobre
    los visibles: **el polígono recupera su relleno** (arregla el pain
    point 2).
  - El caption *"N of 6 dimensions shown"* está siempre, para que ocultar
    algo nunca sea silencioso.
- **Ventaja**: es literalmente el filtro pedido; resuelve el dolor de la
  silueta y permite subconjuntos comparables (p. ej. solo las 3 de calidad).
- **Desventaja**: más código y más tests; un usuario puede ocultar contexto
  (mitigado: tarjetas intactas + caption).

### Opción C — Híbrido focus + hide sobre cards clicables

Cada tarjeta se convierte en el control: enfocar resalta su eje, ocultarlo lo
elimina del radar.

```
┌─────────────────────────────────────────────────────────────────────┐
│ AAPL · Apple Inc.                                                   │
│ Price  $265.32            Data quality HIGH                         │
│ Technology · Consumer Electronics              ┌─────────────────┐  │
│                                                │      Mixed       │  │
│                                                │     Overall      │  │
│                                                └─────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  Click to focus · Shift+click to hide   ⚠ Shift+click NO existe en   │
│                                        táctil (Phase 6)             │
│ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐    │
│ │ Growth       9/10 │ │ Profitability 10/10│ │ Financial H.  5/10│   │
│ │ [Focus]  [eye ON] │ │ [Focus]  [eye ON] │ │ [Focus]  [eye ON] │    │
│ ├───────────────────┤ ├───────────────────┤ ├───────────────────┤    │
│ │ Valuation     4/10│ │ Shareholder R.  — │ │ Management/Moat 7 │    │
│ │ [Focus]  [eye ON] │ │ [Focus]  [eye OFF]│ │ [Focus ◀ enfocado]│    │
│ └───────────────────┘ └───────────────────┘ └───────────────────┘    │
│   (Shareholder Returns oculto: eye OFF; Management/Moat enfocado)    │
├─────────────────────────────────────────────────────────────────────┤
│                            Growth 9                                 │
│                              ▲                                      │
│                             ╱ ╲                                     │
│                 Mgmt 7     ╱   ╲     Profitability 10               │
│                           ╱  ●  ╲   (Management/Moat resaltado)      │
│                          ╱       ╲                                  │
│             Valuation 4 ╱───────╲ Financial Health 5                 │
│   Not scored: ninguno oculto-dato → caption completo                 │
│   (5 de 6 ejes: Shareholder Returns oculto)                          │
└─────────────────────────────────────────────────────────────────────┘
```

- **Comportamiento**: estado (foco + ocultos) en `st.session_state`; el radar
  se dibuja con los ejes visibles y resalta el enfocado. **Realidad Streamlit
  verificada**: `st.container(border=True)` **no es clicable** — no hay
  `on_click` en ninguna tarjeta hoy — así que C exige **añadir** un control
  por tarjeta (botón/pill/checkbox dentro del contenedor): es código nuevo
  encima de las tarjetas, no un click "gratis".
- **Ejes `—` (obligatorio responder)**: la tarjeta muestra `—/10` como hoy
  (badge "not scored"); el eje entra al radar con la política del estado
  actual (ruptura, sin relleno, caption) **hasta que el usuario lo oculta**;
  al ocultarlo, `has_gap` se recalcula (relleno recuperado). Opción de diseño
  discutible: ¿empezar con los `—` ocultos? → pregunta abierta 3.
- **Ventaja**: descubrible (los controles viven en las tarjetas que ya se
  leen), combina drilling + filtrado.
- **Desventajas**: Shift+click inviable en táctil (deuda Phase 6); más
  superficie de estado (foco ∪ ocultos); riesgo WCAG AA mayor (controles
  propios por tarjeta en vez de widgets nativos del tema); el "click en la
  tarjeta" hoy no significa nada, así que hay que inventar la affordance y
  explicarla.

---

## 5. Tabla comparativa

Estimaciones ancladas al código leído (no a la intuición): A toca el resaltado
(`ui/charts.py` + `ui/pages/02_analysis.py`), B filtra **en la página** (el
`radar_figure(dimensions)` actual ya acepta cualquier lista → `ui/charts.py`
probablemente **ni se toca**), C añade estado + control por tarjeta.

| Criterio | A — Focus pulido | B — Multi-select | C — Híbrido cards |
|---|---:|---:|---:|
| Líneas de código (est., impl + tests) | ~30–55 | ~100–160 | ~180–260 |
| Ficheros tocados | 2 (`02_analysis.py`, `charts.py`) | 1–2 (`02_analysis.py` ± tests) | 2–3 (`02_analysis.py`, `charts.py`, tests) |
| Tests nuevos (est.) | 1–2 (adaptar el de opciones del focus si cambia el copy) | 3–5 (multiselect: default 6/6, filtrado, guard N≥3, caption) | 4–6 (foco, ocultado, estado combinado, guard) |
| Riesgo UX | bajo | medio | medio-alto |
| Valor incremental | bajo — **no implementa el filtro pedido** | **alto** — es el filtro pedido | medio-alto |
| Reversibilidad | trivial (kwarg opcional) | fácil (quitar widget ⇒ render actual) | media (estado nuevo en tarjetas) |
| Mobile (Phase 6) | ✅ `selectbox` nativo | ✅ `multiselect` nativo (chips envueltos) | ⚠️ **Shift+click inviable en táctil**; affordance nueva |
| WCAG AA | ✅ sin HTML nuevo; resaltado con la paleta existente (`NEON_CYAN`) | ✅ widgets nativos ya presentes en la UI (screener) y en el baseline visual del tema | ⚠️ controles propios por tarjeta ⇒ contraste a validar caso a caso |
| ¿Resuelve el gap multi-dimensión? | ❌ (sigue single-select) | ✅ | ✅ (vía ocultado) |
| Eje `—` gestionable por el usuario | ❌ (siempre gap) | ✅ (ocultarlo devuelve el relleno) | ✅ |

---

## 6. Mi recomendación

**Opción recomendada: B — multi-select con guard N ≥ 3.**

Razonamiento explícito:

1. **Es el pedido literal.** El diseño original dice *"choose which
   dimensions to display in the radar"*. A no toca el radar (solo lo
   resalta); C lo toca vía ocultado, pero pagando el peaje mobile y de
   affordance. B es la única que entrega exactamente lo que se pidió.
2. **El coste real es menor de lo que parece.** `radar_figure(dimensions)`
   (`ui/charts.py:39`) ya acepta cualquier lista: filtrar en la página antes
   de llamarlo implica **cero cambios en `charts.py`** (la sublista alimenta
   `radar_data`, `radar_missing` y el caption de forma coherente). Precedentes
   de `st.multiselect`/`st.checkbox` ya están en 8 sitios de esta UI — sin
   widgets nuevos ni CSS nuevo, con el contraste heredado del tema (WCAG AA
   sin esfuerzo extra).
3. **El riesgo de "esconder información" es ~0, y lo digo sin maquillaje:**
   las tarjetas de abajo siguen mostrando las 6 dimensiones siempre; el
   filtro es puramente visual sobre el radar. El caption *"N of 6 shown"*
   hace cualquier ocultado explícito.
4. **Arregla un dolor verificado del render actual:** un solo eje `—` quita
   el relleno al polígono entero (`ui/charts.py:48,55`); desmarcar ese eje
   devuelve la forma. Hoy es imposible, con B es un click.
5. **Reversible y barato de descartar:** quitar el widget devuelve el estado
   actual byte a byte (default 6/6 ⇒ `verify_theme` no se mueve), y al ser
   nativo mobile no crea deuda para Phase 6.

**Riesgo que asumo con B:** (a) polígonos degenerados con <3 ejes → guard
deshabilitando el un-check con 3 activas; (b) usuarios que ocultan y luego
"olvidan" que están viendo un subconjunto → mitigado por el caption y por
las tarjetas completas; (c) es la opción con más tests nuevos (~3–5), y
`test_focus_selector_lists_the_dimensions` debe seguir en pie (el focus
picker no se toca).

**Si dijeras "lo más barato":** **A**, o directamente *"mantener el actual +
pulir el copy"*. A con ~30–55 líneas arregla el mayor defecto perceptivo —
que el picker parezca roto porque el radar no reacciona — sin cambiar
layout. Mantener tal cual es defendible solo si el filtro no te interesa:
el dato (las 6 puntuaciones) ya está completo en pantalla; lo que falta es
comodidad visual, no información.

**Si dijeras "lo más completo":** **B con guard N ≥ 3** (+ opcionalmente el
resaltado de A, que convive sin conflicto). **No recomiendo C** aunque sea lo
más completo en papelería: Streamlit no hace clicables los contenedores
(verificado), Shift+click es deuda Phase 6, y su superficie propia de
contraste la hace la peor candidata a WCAG AA.

---

## 7. Preguntas abiertas para el humano

1. **¿Qué opción?** A (focus pulido), B (multi-select, recomendada) o C
   (híbrido) — o *"mantener el actual y solo pulir copy"*. Todo lo demás de
   este documento depende de esta respuesta.
2. **¿Alcance y persistencia del filtro?** ¿Solo el radar (recomendado: las
   tarjetas siguen con las 6) o también tarjetas? ¿La selección vive en
   `session_state` (se pierde al recargar), en **URL query param** (primer
   uso de `st.query_params` en `ui/` — patrón nuevo, pero compartible) o en
   ambos? ¿Se comparte entre tickers (recomendado: comparar la misma forma
   en 2 empresas) o es por ticker como el focus actual?
3. **¿Política de los ejes `—` y mínimo N?** Guard estricto de N ≥ 3
   (deshabilitar un-check, recomendado) o permitir 1–2 con aviso. ¿Los ejes
   sin puntuar se muestran por defecto (estado actual, recomendado) o se
   ocultan por defecto para que el polígono salga relleno?
4. **¿Phase 6 (mobile parity) cambia la decisión?** El multiselect nativo de
   B sí es viable en táctil; el Shift+click de C no. Si mobile es prioridad
   inmediata, C queda descartada ya mismo.
5. **¿El focus picker se conserva tal cual en B?** (Recomendado: sí — abre
   las reglas, es orthogonal al filtro.) ¿O aprovechamos para cambiar su
   copy *"Focus a dimension (opens its rules)"* — p. ej. *"Open a
   dimension's rules"* — que hoy confunde al no mencionar el radar?

---

*Documento de diseño (Fase C.1, rama `feat/radar-filter`). Implementación
pendiente de aprobación humana (C.2). Sin cambios en `ui/`, `backend/` ni
`tests/`.*
