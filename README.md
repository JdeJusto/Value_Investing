# Value Investing

Backend de análisis fundamental (Value Investing) para evaluar empresas mediante
múltiplos financieros, indicadores de calidad, valor intrínseco y scoring compuesto.

## Características

- Obtención de datos financieros vía **yfinance** (Yahoo Finance) y **EDGAR** (SEC)
- 19 métricas fundamentales: ROE, ROIC, FCF Yield, EV/EBIT, Piotroski F-Score,
  Altman Z-Score, DCF, Shareholder Yield, etc.
- Score compuesto ponderado para ranking de empresas
- Estrategia híbrida yfinance + EDGAR con fallback automático
- Salida CSV con análisis completo
- Arquitectura limpia preparada para escalar

## Requisitos

- Python >= 3.11
- Pipenv

## Instalación

```bash
git clone <repo-url>
cd Value_Investing
pipenv install --dev
```

El entorno virtual se crea automáticamente en `.venv/`.

## Visual Studio Code

El proyecto incluye configuración lista para VS Code en `.vscode/`:

1. Abre la carpeta del proyecto en VS Code.
2. Si no lo hiciste ya, ejecuta `pipenv install --dev` para crear el entorno.
3. El intérprete Python se selecciona automáticamente (`.venv/bin/python`).
4. Cada terminal nueva activa el entorno automáticamente.
5. Extensiones recomendadas: Python, Pylance, Black, isort, autoDocstring.

## Configuración

Copia `.env.example` a `.env` y completa los valores:

```bash
cp .env.example .env
```

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `SEC_EMAIL` | Email para identificación en EDGAR | tu-email@ejemplo.com |
| `SEC_NAME` | Nombre para identificación en EDGAR | Tu Nombre |
| `OUTPUT_DIR` | Directorio de salida de CSVs | outputs |

## Ejecución

```bash
pipenv run python main.py
```

## Estructura del proyecto

```
.
├── main.py                       # Entry point
├── backend/                      # Código fuente principal
│   ├── app/
│   │   └── cli.py                # CLI entry point
│   ├── domain/
│   │   ├── entities/             # Company, FinancialStatement, etc.
│   │   ├── value_objects/
│   │   ├── enums/
│   │   └── interfaces/           # Provider, Repository, Cache ABCs
│   ├── providers/
│   │   ├── yahoo/client.py       # Proveedor Yahoo Finance
│   │   ├── edgar/client.py       # Proveedor EDGAR SEC
│   │   └── cache/memory.py       # Caché en memoria
│   ├── repositories/             # Acceso a datos
│   ├── services/                 # Lógica de aplicación
│   ├── analytics/
│   │   ├── analyzer.py           # StockAnalyzer (19 métricas)
│   │   ├── interpretation.py     # Presentación de métricas
│   │   ├── ratios/
│   │   ├── scoring/
│   │   └── valuation/
│   ├── parsers/xbrl/             # Parseo de datos
│   ├── config/settings.py        # Configuración centralizada
│   ├── utils/
│   │   ├── input.py              # Entrada por consola
│   │   └── logging.py            # Logging profesional
│   ├── exceptions/               # Excepciones específicas
│   ├── logging/                  # Config logging
│   └── scripts/
│       └── explore_labels.py     # Script de exploración
├── data/
│   ├── raw/
│   ├── processed/
│   └── cache/
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
├── Pipfile
├── setup.cfg
└── .env.example
```

## Herramientas de desarrollo

```bash
# Formatear código
pipenv run black .
pipenv run isort .

# Linter
pipenv run flake8

# Tests
pipenv run pytest
```

## Arquitectura

El proyecto sigue principios de **Clean Architecture**:

- **Domain**: Entidades puras sin dependencias externas (ni pandas, ni yfinance, ni requests)
- **Providers**: Cada fuente de datos está completamente aislada e implementa interfaces comunes
- **Analytics**: Toda la lógica financiera separada en módulos independientes
- **Repositories**: Acceso a datos desacoplado de los servicios
- **Config**: Configuración centralizada sin constantes repartidas

Las dependencias fluyen hacia adentro: `App → Services → Domain ← Providers`

## Licencia

Uso interno / educativo.
