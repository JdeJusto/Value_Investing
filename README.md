# Value Investing

Backend de análisis fundamental (Value Investing) para evaluar empresas mediante múltiplos financieros, indicadores de calidad, valor intrínseco y scoring compuesto.

## Características

- Obtención de datos financieros vía **yfinance** (Yahoo Finance) y **EDGAR** (SEC)
- 19 métricas fundamentales: ROE, ROIC, FCF Yield, EV/EBIT, Piotroski F-Score, Altman Z-Score, DCF, Shareholder Yield, etc.
- Score compuesto ponderado para ranking de empresas
- Estrategia híbrida yfinance + EDGAR con fallback automático
- Salida CSV con análisis completo

## Requisitos

- Python >= 3.11
- Pipenv

## Instalación

```bash
# Clonar el repositorio
git clone <repo-url>
cd Value_Investing

# Crear entorno Pipenv e instalar dependencias
pipenv install --dev

# Activar el entorno virtual
pipenv shell
```

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

El programa solicitará uno o varios tickers por consola y mostrará el análisis completo en terminal.

## Estructura del proyecto

```
.
├── main.py                       # Punto de entrada
├── analyzer.py                   # Lógica de análisis (StockAnalyzer)
├── consola.py                    # Entrada por consola
├── calculos/
│   └── datos_basicos.py          # Capa de extracción de datos (yfinance)
├── prueba.py                     # Script de exploración (desarrollo)
├── project/
│   ├── app/                      # Aplicación principal (futuro)
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py           # Configuración centralizada
│   ├── services/                 # Servicios de negocio (futuro)
│   ├── providers/                # Proveedores de datos (futuro)
│   ├── models/                   # Modelos de datos (futuro)
│   ├── utils/                    # Utilidades (futuro)
│   ├── cache/                    # Caché de datos
│   ├── data/                     # Datos locales
│   ├── scripts/                  # Scripts auxiliares (futuro)
│   ├── tests/                    # Tests unitarios (futuro)
│   └── docs/                     # Documentación (futuro)
├── Pipfile                       # Dependencias del proyecto
├── setup.cfg                     # Configuración de herramientas
├── .env.example                  # Ejemplo de variables de entorno
└── .gitignore
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

## Licencia

Uso interno / educativo.
