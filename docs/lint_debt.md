# Lint debt

Estado tras la limpieza del **2026-09-29**: `ruff check .` pasa de **983 a 50
errores**. El sprint aplicó autofixes mecánicos por lotes (imports, typing
moderno, `datetime.UTC`, simplificaciones) y documentó los catch-all
intencionales con `# noqa` + razón. La configuración mínima vive en
`ruff.toml` (`target-version = py314` y la excepción de FastAPI para B008).

## Bugs corregidos después del sprint (F821 eliminado)

- **`YahooFinanceProvider.get_wacc`** referenciaba nombres inexistentes y
  devolvía siempre 0.08. Corregido delegando en la nueva función compartida
  `backend/valuation/wacc.py::compute_wacc` (mismas constantes que el DCF),
  usada también por `DCFValuation._wacc`. Commit `c3b8aae`.
- **`backend/app/cli.py`** usaba `CompanyRepository` sin importarlo (solo
  estaba importado dentro de `build_data_pipeline`); los `except` amplios
  enmascaraban el `NameError`. Ambos usos ahora importan el adaptador de
  forma perezosa y capturan solo `(SQLAlchemyError, OSError)`, de modo que
  futuros `NameError` afloran. Se eliminó además la definición duplicada
  muerta de `build_financial_repository` (F811). Commit `5b140d6`.

## Remanente (50) y por qué

| Código | Nº | Motivo / plan |
| --- | --- | --- |
| SIM117 / SIM102 | 14 | Fusión de `with`/`if` anidados con comentarios intercalados; ruff no los autocorrige. Cosmético. |
| DTZ001 / DTZ005 | 9 | `datetime` naive preexistente; añadir tzinfo cambia semántica en comparaciones → requiere revisión caso a caso. |
| F401 | 3 | Re-exports protegidos en `__init__.py` (ruff no los elimina por diseño). |
| C408, F811, PLR0124, RUF007, RUF012, PLW1510, S112, B017, SIM103, PLC0206, PERF402, RUF034, SIM211, F601 | 25 | Casos aislados que requieren revisión individual; algunos son intencionales (`S112`/`B017` en tests). |

## Cómo se hizo (para futuros sprints)

- `ruff check . --fix` **siempre con el conjunto completo de reglas**: un
  `--select` estrecho hace que `RUF100` juzgue los `# noqa` como no usados y
  los elimine (pasó una vez con 160 suppressions; se revirtió).
- Los catch-all de frontera (red/parsers/telemetría) llevan
  `# noqa: BLE001 — boundary catch-all ...` con la razón inline.
- Cada lote se validó con la suite completa antes de commitear.
