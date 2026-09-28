# Web frontend / Interfaz web

## English

This React + TypeScript application is the web client for the Value Investing FastAPI service. It is separate from the Streamlit analysis UI in `../ui/`. API requests use `/api/v1`; the Vite development server proxies them to `http://localhost:8000`.

Requirements: Node.js 22+.

```bash
npm ci
npm run dev       # http://localhost:5173
npm run lint
npm run build
```

Run the FastAPI service separately for authenticated and data-backed pages. The root `docker-compose.yml` also defines the API and Nginx-served frontend for local development.

## Español

Esta aplicación React + TypeScript es el cliente web del servicio FastAPI de Value Investing. Es independiente de la interfaz de análisis Streamlit ubicada en `../ui/`. Las peticiones usan `/api/v1`; el servidor de desarrollo Vite las redirige a `http://localhost:8000`.

Requisitos: Node.js 22+.

```bash
npm ci
npm run dev       # http://localhost:5173
npm run lint
npm run build
```

Ejecuta el servicio FastAPI por separado para las páginas autenticadas y conectadas a datos. El `docker-compose.yml` raíz también define la API y el frontend servido por Nginx para desarrollo local.
