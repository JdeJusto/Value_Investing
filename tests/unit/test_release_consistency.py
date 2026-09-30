"""Consistencia del release: versión ↔ CHANGELOG ↔ metadatos.

Valida que ``backend.__version__`` coincide con la primera entrada del
CHANGELOG, el formato Keep a Changelog (fecha ISO en cada release, secciones
y orden), la versión declarada en ``pyproject.toml`` si existiera y los
badges de versión de los README. Así el script ``scripts/release.sh`` no
puede dejar el repositorio descuadrado.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

SEMVER = r"\d+\.\d+\.\d+"
RELEASE_LINE = re.compile(
    rf"^## \[({SEMVER})\] - (\d{{4}}-\d{{2}}-\d{{2}})\s*$", re.MULTILINE
)
HEADER_LINE = re.compile(r"^## \[(.+?)\](?: - (.+?))?\s*$", re.MULTILINE)
SECCION_LINE = re.compile(r"^### (.+?)\s*$")


def changelog_text() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def clave_version(version: str) -> tuple[int, int, int]:
    return tuple(int(parte) for parte in version.split("."))  # type: ignore[return-value]


def test_version_matches_top_changelog_entry():
    releases = RELEASE_LINE.findall(changelog_text())
    assert releases, "CHANGELOG.md no tiene ninguna entrada '## [x.y.z] - YYYY-MM-DD'"
    assert releases[0][0] == __version__, (
        f"backend.__version__ ({__version__}) no coincide con la primera entrada "
        f"del CHANGELOG ({releases[0][0]})"
    )


def test_changelog_es_keep_a_changelog():
    encabezados = HEADER_LINE.findall(changelog_text())
    assert encabezados, "CHANGELOG.md sin encabezados '## [...]'"

    versiones: list[str] = []
    for version, fecha in encabezados:
        if version.lower() == "unreleased":
            assert not fecha, "la sección 'Unreleased' no lleva fecha"
            continue
        assert re.fullmatch(SEMVER, version), f"versión no semántica: {version!r}"
        assert fecha and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha), (
            f"la entrada {version} no tiene fecha ISO (YYYY-MM-DD): {fecha!r}"
        )
        versiones.append(version)

    assert versiones == sorted(versiones, key=clave_version, reverse=True), (
        "las versiones del CHANGELOG no están en orden descendente"
    )
    assert len(versiones) == len(set(versiones)), (
        "hay versiones duplicadas en el CHANGELOG"
    )


def test_cada_release_tiene_secciones():
    """Cada versión publicada debe tener al menos una sección (### Added/...)."""
    releases_sin_seccion: list[str] = []
    version_actual = ""
    en_release = False
    tiene_seccion = False

    for linea in changelog_text().splitlines():
        encabezado = re.match(r"^## \[(.+?)\]", linea)
        if encabezado:
            if en_release and not tiene_seccion:
                releases_sin_seccion.append(version_actual)
            version_actual = encabezado.group(1)
            en_release = version_actual.lower() != "unreleased"
            tiene_seccion = False
            continue
        if en_release and SECCION_LINE.match(linea):
            tiene_seccion = True

    if en_release and not tiene_seccion:
        releases_sin_seccion.append(version_actual)

    assert not releases_sin_seccion, (
        f"estas versiones del CHANGELOG no tienen ninguna sección (### ...): "
        f"{releases_sin_seccion}"
    )


def test_pyproject_version_matches_backend():
    if not PYPROJECT.exists():
        pytest.skip("no hay pyproject.toml (las dependencias viven en Pipfile)")
    coincidencia = re.search(
        r"""^[ \t]*version[ \t]*=[ \t]*["']([^"']+)["']""",
        PYPROJECT.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not coincidencia:
        pytest.skip("pyproject.toml sin campo version")
    assert coincidencia.group(1) == __version__, (
        f"pyproject.toml ({coincidencia.group(1)}) y backend.__version__ "
        f"({__version__}) no coinciden"
    )


def test_badges_de_version_de_los_readme():
    for nombre in ("README.md", "README.es.md"):
        ruta = REPO_ROOT / nombre
        if not ruta.exists():
            continue
        coincidencia = re.search(
            r"badge/version-(\d+\.\d+\.\d+)-", ruta.read_text(encoding="utf-8")
        )
        if coincidencia:
            assert coincidencia.group(1) == __version__, (
                f"{nombre} muestra la versión {coincidencia.group(1)} pero el paquete "
                f"es {__version__}"
            )
