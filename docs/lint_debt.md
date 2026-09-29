# Lint debt

Estado tras la limpieza del **2026-09-29**: `ruff check .` pasa de **983 a 62
errores**. El sprint aplicó autofixes mecánicos por lotes (imports, typing
moderno, `datetime.UTC`, simplificaciones) y documentó los catch-all
intencionales con `# noqa` + razón. La configuración mínima vive en
`ruff.toml` (`target-version = py314` y la excepción de FastAPI para B008).

## Remanente (62) y por qué

| Código | Nº | Motivo / plan |
| --- | --- | --- |
| **F821** | 11 | **Bugs reales descubiertos — NO arreglados en el sprint** (regla: documentar, no arreglar en silencio):<br>• `backend/providers/yahoo/provider.py::get_wacc` referencia variables inexistentes (`beta`, `financials`, `weight_equity`, ...); el `except` lo traga y **siempre devuelve 0.08**. Follow-up: reimplementarlo con `PriceService.get_beta`/coste de deuda o retirarlo.<br>• `backend/app/cli.py::_tracked_tickers`/`_company_enrichment` usan `CompanyRepository` **sin import**; los `except` lo enmascaran y caen siempre al fallback silencioso. Follow-up: importar el adaptador (o retirar el camino muerto).<br>• Resto: anotaciones que referencian imports perezosos ya cubiertas con `TYPE_CHECKING` en yahoo/edgar; quedan las de `get_wacc`. |
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
