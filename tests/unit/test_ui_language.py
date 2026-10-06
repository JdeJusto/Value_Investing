"""Guard: user-facing strings in ui/ must be English.

Heuristic: it flags common Spanish words that should not appear in string
literals. Comments and docstrings are ignored — they may stay in any
language. False negatives are acceptable; false positives are not.
"""

from __future__ import annotations

import ast
from pathlib import Path

SPANISH_MARKERS = [
    "Precio",
    "Categoría",
    "Último",
    "Última",
    "Señal",
    "Añadir",
    "Métrica",
    "Valor por defecto",
    "Sin datos",
    "Ningún",
    "El universo",
    "Resumen de",
    "Posición",
    "El análisis",
]


def _docstring_constants(tree: ast.AST) -> set[int]:
    """Ids of Constant nodes used as docstrings (documentation, not UI text)."""
    ids: set[int] = set()
    scope_nodes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, scope_nodes):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def test_no_spanish_strings_in_ui():
    ui_dir = Path(__file__).resolve().parents[2] / "ui"
    offenders = []
    for path in sorted(ui_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_constants(tree)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                continue
            for marker in SPANISH_MARKERS:
                if marker in node.value:
                    offenders.append(f"{path}:{node.lineno}: {node.value[:80]}")
    assert not offenders, "Spanish strings found:\n" + "\n".join(offenders)
