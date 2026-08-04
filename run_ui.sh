#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_STREAMLIT="$SCRIPT_DIR/.venv/bin/streamlit"

if [ ! -f "$VENV_STREAMLIT" ]; then
    echo "Streamlit no encontrado en .venv. Ejecutando pipenv install..."
    pipenv install
fi

echo "Arrancando Value Investing UI..."
echo "Abre http://localhost:8501 en tu navegador"
"$VENV_STREAMLIT" run "$SCRIPT_DIR/ui/app.py"
