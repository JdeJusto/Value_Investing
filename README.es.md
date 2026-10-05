# Value Investing

[English](README.md) · [Español](README.es.md)

[![Version](https://img.shields.io/badge/version-0.10.2-blue)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-1324%20passed-green)]()

Herramienta determinista y explicable para el análisis fundamental de acciones. Combina estados financieros, métricas transparentes de valoración y calidad, filtros, seguimiento de carteras y backtesting mediante una interfaz de terminal y aplicaciones web.

> **Principio de diseño:** «Los tontos admiran la complejidad; los genios admiran la simpleza». Se prefieren reglas claras, componentes pequeños y datos trazables antes que complejidad que no aporte valor.

## Qué incluye la 0.1.0

Primera release pública: siete metodologías derivadas de libros (Graham, Graham & Dodd, Buffett/Clark, Buffett Classic, Fisher, Lynch GARP y Greenblatt Magic Formula), valoración DCF con cuatro variantes, fundamentales de la SEC a través de Financial-DataBase, UI Streamlit de cinco páginas, screener, cartera, workflow diario y alertas. Los precios se obtienen bajo demanda y nunca se persisten. Véase [CHANGELOG.md](CHANGELOG.md) para la lista completa y las limitaciones conocidas.

## Qué ofrece

- Carga y normalización de fundamentales de SEC EDGAR, Yahoo Finance o el proyecto complementario Financial-DataBase.
- Cálculo de ratios, valoraciones DCF, calidad empresarial y moat, con puntuaciones explicables.
- Filtros y ranking de empresas, oportunidades y alertas fundamentales.
- Seguimiento de carteras y backtesting histórico determinista.
- CLI, interfaz de análisis Streamlit y aplicación web FastAPI + React.

Es una herramienta de análisis, **no asesoramiento financiero**. Los resultados dependen de la calidad y disponibilidad de los datos externos.

## Fuentes de datos y servicios externos

| Fuente | Uso |
| --- | --- |
| [SEC EDGAR](https://www.sec.gov/edgar) | Presentaciones regulatorias, hechos XBRL e identificadores de empresa/CIK. El proveedor directo usa `edgartools`; Financial-DataBase también puede actualizar datos SEC. Las peticiones requieren un `SEC_USER_AGENT` descriptivo con datos de contacto válidos. |
| [Yahoo Finance](https://finance.yahoo.com/) mediante [`yfinance`](https://github.com/ranaroussi/yfinance) | Datos de mercado, precios bajo demanda y fuente alternativa de estados financieros. Los precios se guardan temporalmente en memoria y **este proyecto no los persiste**. Yahoo controla su disponibilidad y límites de uso. |
| [Wikipedia](https://www.wikipedia.org/) | Listas de componentes para reconstruir los universos del S&P 500, Nasdaq-100 y algunos índices europeos. |
| [iShares](https://www.ishares.com/) | Componentes del Russell 2000 a partir del fichero oficial de posiciones del ETF IWM. |
| [Financial-DataBase](https://github.com/JdeJusto/Financial-DataBase) | Base de datos PostgreSQL complementaria, opcional, para fundamentales SEC y actualizaciones SEC dirigidas. Es un proyecto independiente y se configura con `FINANCIAL_DATABASE_URL`. |

Los datos y marcas de terceros no están cubiertos por la licencia MIT de este repositorio. Respeta las condiciones, políticas de acceso y requisitos de atribución de cada proveedor. Los datos pueden estar retrasados, incompletos o no disponibles.

Las integraciones Python usan `edgartools`, `yfinance` y SQLAlchemy. Las
interfaces son Streamlit y FastAPI + React; la pila opcional de Compose también
usa Redis y Celery. `Pipfile` y `Pipfile.lock` son la lista de dependencias
Python de referencia.

## Inicio rápido

Requisitos: Python 3.13+ (versión usada en CI) y Pipenv. PostgreSQL y Docker Compose son opcionales para la CLI; Node.js 22+ solo hace falta para desarrollar el frontend React.

```bash
git clone https://github.com/JdeJusto/Value_Investing.git
cd Value_Investing
python -m pip install pipenv
pipenv install --dev
cp .env.example .env
```

Edita `.env` antes de hacer peticiones a SEC. Sustituye el `SEC_USER_AGENT` de ejemplo por el nombre descriptivo de la aplicación y un correo real de contacto. Configura `SEC_EMAIL` y `SEC_NAME` para el proveedor directo `edgartools`. No publiques `.env` ni credenciales reales.

```bash
./vi debug
./vi load-data AAPL
./vi analyze AAPL
./vi screener --tickers AAPL,MSFT
./run_ui.sh                 # interfaz Streamlit en http://localhost:8501
```

`./vi` utiliza el entorno virtual del proyecto sin necesitar `pipenv run`. La lista completa de variables está en [`.env.example`](.env.example). `FINANCIAL_DATABASE_URL` es opcional; si Financial-DataBase no está disponible, la aplicación puede usar su repositorio JSON local y los proveedores configurados.

La pila opcional de Docker Compose incluye PostgreSQL, Redis, el servicio FastAPI, workers de Celery y el frontend React. Está pensada para desarrollo local, no para producción; configura secretos, migraciones de base de datos y acceso de red antes de exponer cualquier servicio.

## Pruebas

```bash
pipenv run python -m pytest tests/unit -q
```

Las pruebas unitarias no necesitan datos de mercado en vivo ni una base de datos. Las pruebas que requieren Financial-DataBase se omiten si no está configurado.

## Estructura del proyecto

```text
backend/      dominio, proveedores, repositorios, analítica, servicios y API
cli/          comandos de terminal
ui/           interfaz de análisis Streamlit
frontend/     cliente React + TypeScript para el servicio FastAPI
scripts/      flujo diario, construcción de universos, validación y utilidades de desarrollo
config/       universo y configuración de ejecución
tests/        pruebas automatizadas
data/         datos del repositorio local, caché e informes
```

## Documentación

- [Flujo diario](docs/runbook_daily.md)
- [Metodología de puntuación](docs/scoring_methodology.md) y [validación](docs/scoring_validation.md)
- [Metodología de validación entre fuentes](docs/validation_methodology.md)
- [Contribuir](CONTRIBUTING.md) · [Seguridad](SECURITY.md) · [Código de conducta](CODE_OF_CONDUCT.md)

## Publicación de versiones

Las versiones siguen [Versionado Semántico](https://semver.org/lang/es/). Consulta el proceso en [CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## Licencia

[MIT](LICENSE). La licencia cubre el código de este proyecto, no los datos proporcionados por terceros.
